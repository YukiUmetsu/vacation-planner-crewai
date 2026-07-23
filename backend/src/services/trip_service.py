"""Trip orchestration: create, route confirm, plan-next-day."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any, Callable

from pydantic import ValidationError

from crews.runner import CrewRunner, crew_mode, get_crew_runner
from db import repository as repo
from db.place_keys import make_place_key
from db.protocols import DynamoDBTable
from http_utils import ApiError, client_facing_message, public_item
from models.api import ConfirmCitiesRequest, CreateTripRequest, UpdateTripRequest
from services.crew_context_budget import slim_crew_inputs
from services.dates import date_for_day_index, parse_iso_date, validate_trip_dates
from services.dedupe import dedupe_places
from services.energy import clamp_energy_level, max_minutes_for_energy
from services.route_windows import normalize_route_windows
from services.place_quality import (
    day_total_minutes,
    filter_quality_places,
    profile_visited_name_keys,
    validate_suggested_place,
)
from services.plan_day_worker import (
    enqueue_plan_next_day_worker,
    plan_next_day_async_enabled,
)
from services.places_enrich import enrich_place, enrich_places
from services.profile_service import ProfileService
from services.safety import SafetyGate, get_safety_gate
from services.worker_observability import WorkerTimer, log_crew_duration


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    return value


def _validate(model_cls: type, body: dict[str, Any]) -> Any:
    try:
        return model_cls.model_validate(body)
    except ValidationError as exc:
        raise ApiError(400, str(exc.errors()[0]["msg"]) if exc.errors() else "invalid request") from exc


def _split_bundle(items: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    trip = None
    route = None
    days: list[dict[str, Any]] = []
    for item in items:
        et = item.get("entity_type")
        if et == "TRIP":
            trip = item
        elif et == "ROUTE":
            route = item
        elif et == "DAY":
            days.append(item)
    days.sort(key=lambda d: int(d.get("day_index") or 0))
    return trip, route, days


def _route_payload(route: dict[str, Any]) -> dict[str, Any]:
    """Strip DynamoDB envelope fields from a ROUTE item for crew/API."""
    skip = {
        "pk",
        "sk",
        "gsi1pk",
        "gsi1sk",
        "entity_type",
        "trip_id",
        "updated_at",
        "created_at",
    }
    return {k: v for k, v in route.items() if k not in skip}


def _sync_total_nights(route: dict[str, Any]) -> dict[str, Any]:
    cities = route.get("cities") or []
    nights_sum = sum(int(c.get("nights") or 0) for c in cities)
    return {**route, "total_nights": nights_sum}


def _assert_route_fits_window(route: dict[str, Any], day_count: int) -> None:
    cities = route.get("cities") or []
    if not cities:
        raise ApiError(
            400,
            "Add or propose at least one city before confirming.",
            code="route_empty",
        )
    covered: set[int] = set()
    for stop in cities:
        arrival = int(stop.get("arrival_day_index") or 0)
        departure = int(stop.get("departure_day_index") or 0)
        if not (1 <= arrival <= day_count and 1 <= departure <= day_count):
            raise ApiError(
                400,
                f"City days must stay within day 1–{day_count}. "
                "Reduce nights or remove a city.",
                code="route_out_of_window",
            )
        if departure < arrival:
            raise ApiError(
                400,
                "Each city must leave on or after the day it arrives.",
                code="route_inverted_stop",
            )
        for day in range(arrival, departure + 1):
            if day in covered:
                raise ApiError(
                    400,
                    f"Cities overlap on day {day}. "
                    "Adjust nights so each day has one overnight city.",
                    code="route_overlap",
                )
            covered.add(day)
    nights_sum = sum(int(c.get("nights") or 0) for c in cities)
    total = int(route.get("total_nights") or nights_sum)
    if total != nights_sum:
        raise ApiError(
            400,
            f"total_nights ({total}) must equal the sum of city nights ({nights_sum}).",
            code="route_total_nights",
        )
    expected_nights = max(0, day_count - 1)
    if nights_sum != expected_nights:
        raise ApiError(
            400,
            f"This route has {nights_sum} overnight night"
            f"{'' if nights_sum == 1 else 's'} but your trip needs "
            f"{expected_nights} (days − 1). Adjust nights or remove a city.",
            code="route_nights_mismatch",
        )
    missing = [day for day in range(1, day_count + 1) if day not in covered]
    if missing:
        raise ApiError(
            400,
            f"Day {missing[0]} is not covered. Add nights or another city "
            "so every trip day is included.",
            code="route_gap",
        )


def overnight_city_for_day(route: dict[str, Any] | None, day_index: int, destination: str) -> str:
    if not route:
        return destination
    for stop in route.get("cities") or []:
        arrival = int(stop.get("arrival_day_index") or 0)
        departure = int(stop.get("departure_day_index") or 0)
        if arrival <= day_index <= departure:
            return str(stop.get("city") or destination)
    raise ApiError(409, f"no city covers day_index={day_index}", code="route_gap")


def _merge_preferences(trip_prefs: str, profile_prefs: str, interests: list[str]) -> str:
    parts: list[str] = []
    for chunk in (trip_prefs.strip(), profile_prefs.strip()):
        if chunk and chunk not in parts:
            parts.append(chunk)
    if interests:
        interest_line = "Interests: " + ", ".join(interests)
        if interest_line not in parts:
            parts.append(interest_line)
    return " | ".join(parts)


def _meal_guidance(*, include_breakfast: bool) -> str:
    """Hard meal requirements appended into crew preferences."""
    base = (
        "Meals: include lunch and dinner as food stops (category=food) "
        "with realistic meal timing in the day's order."
    )
    if include_breakfast:
        return (
            f"{base} Also include breakfast as a food stop "
            "(suggest_include_breakfast=true)."
        )
    return f"{base} Skip breakfast unless the traveler preferences ask for it."


def first_missing_day_index(
    days: list[dict[str, Any]], day_count: int
) -> int | None:
    """Lowest 1-based day_index with no DAY row, or None when the trip is full."""
    planned = {
        int(d.get("day_index") or 0)
        for d in days
        if int(d.get("day_index") or 0) >= 1
    }
    for index in range(1, day_count + 1):
        if index not in planned:
            return index
    return None


def resolve_plan_day_index(
    *,
    trip: dict[str, Any],
    days: list[dict[str, Any]],
) -> int:
    """Day to plan next — fill gaps before trusting a jumped ``next_day_index``."""
    day_count = int(trip["day_count"])
    gap = first_missing_day_index(days, day_count)
    if gap is None:
        raise ApiError(409, "all days already planned", code="complete")
    return gap


def rebuild_prior_days_summary(days: list[dict[str, Any]]) -> str:
    """One-line-per-day summary matching plan-next-day cursor updates."""
    lines: list[str] = []
    for day in sorted(days, key=lambda d: int(d.get("day_index") or 0)):
        index = int(day.get("day_index") or 0)
        if index < 1:
            continue
        theme = str(day.get("theme") or f"Day {index}")
        overnight = str(day.get("overnight_city") or "")
        line = f"Day {index}: {theme} @ {overnight}".strip()
        if line.endswith("@"):
            line = line[:-1].strip()
        lines.append(line)
    return "\n".join(lines)


def visited_keys_from_days(days: list[dict[str, Any]]) -> list[str]:
    """Stable order of unique place_keys across remaining day plans."""
    keys: list[str] = []
    seen: set[str] = set()
    for day in sorted(days, key=lambda d: int(d.get("day_index") or 0)):
        for place in day.get("places") or []:
            if not isinstance(place, dict):
                continue
            key = str(place.get("place_key") or "").strip()
            if key and key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


def status_after_day_edit(
    *,
    remaining_days: list[dict[str, Any]],
    day_count: int,
    previous_status: str,
) -> tuple[int, str]:
    """Return (next_day_index, status) after a day was removed or emptied."""
    gap = first_missing_day_index(remaining_days, day_count)
    if gap is None:
        return day_count + 1, "complete"
    if not remaining_days:
        # Route is still confirmed; traveler can plan again from day 1.
        if previous_status in {"planning", "complete", "failed"}:
            return 1, "routing_confirmed"
        return 1, previous_status or "routing_confirmed"
    return gap, "planning"


def _profile_visited_keys(visited_places: list[Any]) -> list[str]:
    keys: list[str] = []
    for place in visited_places:
        if not isinstance(place, dict):
            continue
        name = str(place.get("name") or "").strip()
        if not name:
            continue
        city = str(place.get("city") or "").strip() or None
        keys.append(make_place_key(name, city))
    return keys


def synthetic_city_route(*, destination: str, day_count: int) -> dict[str, Any]:
    return {
        "destination_type": "city",
        "cities": [
            {
                "city": destination,
                "country": "",
                "nights": max(0, day_count - 1),
                "arrival_day_index": 1,
                "departure_day_index": day_count,
                "reason": "Single-city destination",
                "highlights": [],
            }
        ],
        "rationale": "Destination is a single city; routing skipped",
        "total_nights": max(0, day_count - 1),
        "status": "confirmed",
    }


class TripService:
    def __init__(
        self,
        *,
        table: DynamoDBTable | None = None,
        runner: CrewRunner | None = None,
        safety: SafetyGate | None = None,
        enqueue_plan_day: Callable[[str, str, int], None] | None = None,
    ) -> None:
        self._table = table
        self._runner = runner
        self._safety = safety
        self._enqueue_plan_day = enqueue_plan_day

    @property
    def runner(self) -> CrewRunner:
        if self._runner is None:
            self._runner = get_crew_runner()
        return self._runner

    @property
    def safety(self) -> SafetyGate:
        if self._safety is None:
            self._safety = get_safety_gate()
        return self._safety

    def create_trip(self, user_sub: str, body: dict[str, Any]) -> dict[str, Any]:
        req = _validate(CreateTripRequest, body)
        start, end, day_count = validate_trip_dates(req.start_date, req.end_date)
        self.safety.check_text(req.preferences, source="preferences")
        self.safety.check_text(req.destination, source="destination")

        trip_id = str(uuid.uuid4())
        if req.destination_type == "city":
            status = "routing_confirmed"
        else:
            status = "drafting"

        trip = repo.put_trip(
            user_sub=user_sub,
            trip_id=trip_id,
            origin=req.origin,
            destination=req.destination,
            destination_type=req.destination_type,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            day_count=day_count,
            preferences=req.preferences,
            status=status,
            table=self._table,
        )

        route = None
        if req.destination_type == "city":
            route = repo.put_route(
                user_sub=user_sub,
                trip_id=trip_id,
                route=synthetic_city_route(destination=req.destination, day_count=day_count),
                table=self._table,
            )

        return {
            "trip": public_item(trip),
            "route": public_item(route) if route else None,
        }

    def update_trip(self, user_sub: str, trip_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Update trip details; clears the route so cities can be re-proposed."""
        trip, route, days = self._load_owned_bundle(user_sub, trip_id)
        if days:
            raise ApiError(
                409,
                "Trip days are already planned — start a new trip to change dates.",
                code="bad_status",
            )
        status = str(trip.get("status") or "")
        if status in {"complete", "planning"}:
            raise ApiError(
                409,
                f"cannot edit trip details from status={status!r}",
                code="bad_status",
            )

        req = _validate(UpdateTripRequest, body)
        origin = req.origin if req.origin is not None else str(trip["origin"])
        destination = (
            req.destination if req.destination is not None else str(trip["destination"])
        )
        destination_type = (
            req.destination_type
            if req.destination_type is not None
            else str(trip["destination_type"])
        )
        start_raw = req.start_date if req.start_date is not None else str(trip["start_date"])
        end_raw = req.end_date if req.end_date is not None else str(trip["end_date"])
        preferences = (
            req.preferences if req.preferences is not None else str(trip.get("preferences") or "")
        )

        self.safety.check_text(preferences, source="preferences")
        self.safety.check_text(destination, source="destination")
        start, end, day_count = validate_trip_dates(start_raw, end_raw)

        updates: dict[str, Any] = {
            "origin": origin,
            "destination": destination,
            "destination_type": destination_type,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "day_count": day_count,
            "preferences": preferences,
        }
        # Always invalidate the route: the UI re-proposes after every save, and
        # confirmed/awaiting trips must return to drafting (or a fresh city route).
        repo.delete_route(user_sub=user_sub, trip_id=trip_id, table=self._table)
        if destination_type == "city":
            updates["status"] = "routing_confirmed"
            route = repo.put_route(
                user_sub=user_sub,
                trip_id=trip_id,
                route=synthetic_city_route(
                    destination=destination, day_count=day_count
                ),
                table=self._table,
            )
        else:
            updates["status"] = "drafting"
            route = None

        trip = repo.update_trip(
            user_sub=user_sub,
            trip_id=trip_id,
            updates=updates,
            table=self._table,
        )
        return {
            "trip": public_item(trip),
            "route": public_item(route) if route else None,
        }

    def list_trips(self, user_sub: str) -> dict[str, Any]:
        items = repo.list_trip_meta_for_user(user_sub=user_sub, table=self._table)
        items_sorted = sorted(items, key=lambda t: t.get("created_at") or "", reverse=True)
        return {"trips": [public_item(t) for t in items_sorted]}

    def delete_trip(self, user_sub: str, trip_id: str) -> dict[str, Any]:
        """Remove trip meta, route, and all day-plan rows for an owned trip."""
        self._require_trip(user_sub, trip_id)
        try:
            # Atomic delete lock: fails if a planning claim is held.
            repo.begin_trip_delete(
                user_sub=user_sub, trip_id=trip_id, table=self._table
            )
        except repo.ConcurrentModificationError as exc:
            raise ApiError(
                409,
                "cannot delete trip while planning is in progress",
                code="planning_in_progress",
            ) from exc
        counts = repo.delete_trip_bundle(
            user_sub=user_sub, trip_id=trip_id, table=self._table
        )
        return {"ok": True, "trip_id": trip_id, "deleted": counts}

    def get_trip(self, user_sub: str, trip_id: str) -> dict[str, Any]:
        trip, route, days = self._load_owned_bundle(user_sub, trip_id)
        return {
            "trip": public_item(trip),
            "route": public_item(route) if route else None,
            "days": [public_item(d) for d in days],
        }

    def propose_cities(self, user_sub: str, trip_id: str) -> dict[str, Any]:
        trip = self._require_trip(user_sub, trip_id)
        destination_type = trip["destination_type"]
        if destination_type == "city":
            raise ApiError(409, "city destinations skip propose-cities", code="not_applicable")

        status = trip.get("status")
        if status not in {"drafting", "awaiting_city_confirm"}:
            raise ApiError(409, f"cannot propose cities from status={status!r}", code="bad_status")

        self.safety.check_text(str(trip.get("preferences") or ""), source="preferences")
        self.safety.check_text(str(trip.get("destination") or ""), source="destination")

        inputs = {
            "origin": trip["origin"],
            "destination": trip["destination"],
            "destination_type": destination_type,
            "start_date": trip["start_date"],
            "end_date": trip["end_date"],
            "day_count": str(int(trip["day_count"])),
            "preferences": trip.get("preferences") or "",
        }
        timer = WorkerTimer()
        route_data = normalize_route_windows(
            _sync_total_nights(self.runner.propose_cities(inputs)),
            int(trip["day_count"]),
        )
        log_crew_duration(
            operation="propose_cities",
            trip_id=trip_id,
            duration_ms=timer.duration_ms(),
            extra={"crew_mode": crew_mode()},
        )
        route_data["status"] = "proposed"
        _assert_route_fits_window(route_data, int(trip["day_count"]))

        route = repo.put_route(
            user_sub=user_sub,
            trip_id=trip_id,
            route=route_data,
            table=self._table,
        )
        trip = repo.update_trip(
            user_sub=user_sub,
            trip_id=trip_id,
            updates={"status": "awaiting_city_confirm"},
            table=self._table,
        )
        return {"trip": public_item(trip), "route": public_item(route)}

    def confirm_cities(self, user_sub: str, trip_id: str, body: dict[str, Any]) -> dict[str, Any]:
        trip = self._require_trip(user_sub, trip_id)
        status = trip.get("status")
        if status not in {"awaiting_city_confirm", "drafting", "routing_confirmed"}:
            raise ApiError(409, f"cannot confirm cities from status={status!r}", code="bad_status")

        req = _validate(ConfirmCitiesRequest, body)
        # User-confirmed routes must pass validation as submitted — do not silently
        # rewrite nights/windows (crew proposals are normalized in propose_cities).
        route_data = _sync_total_nights(
            {
                "destination_type": req.destination_type,
                "cities": req.cities,
                "rationale": req.rationale,
                "total_nights": req.total_nights,
                "status": "confirmed",
            }
        )
        _assert_route_fits_window(route_data, int(trip["day_count"]))

        route = repo.put_route(
            user_sub=user_sub,
            trip_id=trip_id,
            route=route_data,
            table=self._table,
        )
        trip = repo.update_trip(
            user_sub=user_sub,
            trip_id=trip_id,
            updates={"status": "routing_confirmed"},
            table=self._table,
        )
        return {"trip": public_item(trip), "route": public_item(route)}

    def plan_next_day(self, user_sub: str, trip_id: str) -> dict[str, Any]:
        """Plan the next day — sync 200 body, or async 202 body when agentcore."""
        if plan_next_day_async_enabled():
            return self.start_plan_next_day(user_sub, trip_id)
        return self._plan_next_day_sync(user_sub, trip_id)

    def start_plan_next_day(self, user_sub: str, trip_id: str) -> dict[str, Any]:
        """Claim planning slot and enqueue worker; returns async response shape."""
        trip, route, days = self._load_owned_bundle(user_sub, trip_id)
        status = trip.get("status")
        if status not in {"routing_confirmed", "planning", "failed"}:
            raise ApiError(
                409, f"cannot plan day from status={status!r}", code="bad_status"
            )

        if trip["destination_type"] != "city":
            if not route or route.get("status") != "confirmed":
                raise ApiError(409, "confirmed city route required", code="route_required")

        # Finish an in-flight claim before filling gaps (orphan DAY after worker Put).
        claimed_raw = trip.get("planning_day_index")
        if claimed_raw is not None:
            try:
                claimed_i = int(claimed_raw)
            except (TypeError, ValueError):
                claimed_i = None
            if claimed_i is not None and claimed_i >= 1:
                recovered = self._finalize_existing_planned_day(
                    user_sub=user_sub,
                    trip_id=trip_id,
                    trip=trip,
                    day_index=claimed_i,
                    ensure_claim=False,
                )
                if recovered is not None:
                    return recovered
                # No DAY yet for the claim — drop only if stuck long enough.
                if repo.clear_stale_planning_claim(
                    user_sub=user_sub, trip_id=trip_id, table=self._table
                ):
                    trip = self._require_trip(user_sub, trip_id)
                else:
                    raise ApiError(
                        409,
                        "a day is already being planned for this trip",
                        code="conflict",
                    )

        next_index = resolve_plan_day_index(trip=trip, days=days)
        stored_next = int(trip.get("next_day_index") or 1)
        if stored_next != next_index:
            # Heal skipped cursor (e.g. claim advanced but DAY put failed).
            trip = repo.update_trip(
                user_sub=user_sub,
                trip_id=trip_id,
                updates={"next_day_index": next_index},
                table=self._table,
            )

        # DAY already present (worker died after Put) — finish cursor without re-crew.
        recovered = self._finalize_existing_planned_day(
            user_sub=user_sub,
            trip_id=trip_id,
            trip=trip,
            day_index=next_index,
            ensure_claim=True,
        )
        if recovered is not None:
            return recovered

        try:
            claimed = repo.claim_planning_in_progress(
                user_sub=user_sub,
                trip_id=trip_id,
                expected_next_day_index=next_index,
                table=self._table,
            )
        except repo.ConcurrentModificationError as exc:
            trip = self._require_trip(user_sub, trip_id)
            recovered = self._finalize_existing_planned_day(
                user_sub=user_sub,
                trip_id=trip_id,
                trip=trip,
                day_index=next_index,
                ensure_claim=False,
            )
            if recovered is not None:
                return recovered
            raise ApiError(409, str(exc), code="conflict") from exc

        enqueue = self._enqueue_plan_day or enqueue_plan_next_day_worker
        try:
            enqueue(user_sub, trip_id, next_index)
        except Exception as exc:
            repo.fail_planning_in_progress(
                user_sub=user_sub,
                trip_id=trip_id,
                planned_day_index=next_index,
                error_message=client_facing_message(
                    status_code=502,
                    code="enqueue_failed",
                    detail=f"failed to start planner: {type(exc).__name__}",
                ),
                table=self._table,
            )
            raise ApiError(
                502,
                client_facing_message(
                    status_code=502,
                    code="enqueue_failed",
                    detail="failed to start async plan-next-day worker",
                ),
                code="enqueue_failed",
            ) from exc

        return {
            "async": True,
            "trip": public_item(claimed),
            "planning_day_index": next_index,
        }

    def execute_plan_next_day(
        self, user_sub: str, trip_id: str, day_index: int
    ) -> dict[str, Any]:
        """Worker path: run crew + enrich + persist for an already-claimed day."""
        trip, route, _days = self._load_owned_bundle(user_sub, trip_id)
        if str(trip.get("status") or "") == "deleting":
            raise ApiError(
                409,
                "trip is being deleted",
                code="trip_deleting",
            )
        claimed = trip.get("planning_day_index")
        try:
            claimed_i = int(claimed) if claimed is not None else None
        except (TypeError, ValueError):
            claimed_i = None
        if claimed_i != day_index:
            raise ApiError(
                409,
                f"planning claim mismatch (expected {day_index}, got {claimed!r})",
                code="claim_mismatch",
            )

        next_index = int(trip.get("next_day_index") or 1)
        if next_index != day_index:
            raise ApiError(
                409,
                "next_day_index no longer matches claimed day",
                code="claim_mismatch",
            )

        recovered = self._finalize_existing_planned_day(
            user_sub=user_sub,
            trip_id=trip_id,
            trip=trip,
            day_index=day_index,
            ensure_claim=False,
        )
        if recovered is not None:
            return recovered

        try:
            return self._run_plan_day_and_persist(
                user_sub=user_sub,
                trip_id=trip_id,
                trip=trip,
                route=route,
                next_index=next_index,
                async_claimed=True,
            )
        except ApiError as exc:
            # Retryable AgentCore transport errors: keep claim so Event retries run.
            if (
                not exc.retryable
                and not self._day_exists(user_sub, trip_id, day_index)
            ):
                repo.fail_planning_in_progress(
                    user_sub=user_sub,
                    trip_id=trip_id,
                    planned_day_index=day_index,
                    error_message=client_facing_message(
                        status_code=exc.status_code,
                        code=exc.code,
                        detail=exc.message,
                    ),
                    table=self._table,
                )
            raise
        except Exception as exc:
            if not self._day_exists(user_sub, trip_id, day_index):
                repo.fail_planning_in_progress(
                    user_sub=user_sub,
                    trip_id=trip_id,
                    planned_day_index=day_index,
                    error_message=client_facing_message(
                        status_code=500,
                        code="internal_error",
                        detail=f"{type(exc).__name__}: {exc}",
                    ),
                    table=self._table,
                )
            raise

    def _day_exists(self, user_sub: str, trip_id: str, day_index: int) -> bool:
        return (
            repo.get_day(
                user_sub=user_sub,
                trip_id=trip_id,
                day_index=day_index,
                table=self._table,
            )
            is not None
        )

    def _finalize_existing_planned_day(
        self,
        *,
        user_sub: str,
        trip_id: str,
        trip: dict[str, Any],
        day_index: int,
        ensure_claim: bool,
    ) -> dict[str, Any] | None:
        """If DAY already exists, advance cursors / clear claim. Returns sync body or None."""
        existing = repo.get_day(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            table=self._table,
        )
        if existing is None:
            return None

        if ensure_claim and trip.get("planning_day_index") is None:
            try:
                trip = repo.claim_planning_in_progress(
                    user_sub=user_sub,
                    trip_id=trip_id,
                    expected_next_day_index=day_index,
                    table=self._table,
                )
            except repo.ConcurrentModificationError:
                trip = self._require_trip(user_sub, trip_id)

        claimed = trip.get("planning_day_index")
        try:
            claimed_i = int(claimed) if claimed is not None else None
        except (TypeError, ValueError):
            claimed_i = None
        if claimed_i != day_index:
            # Cursor already advanced past this day — treat as done.
            if int(trip.get("next_day_index") or 0) > day_index:
                return {
                    "async": False,
                    "day": public_item(existing),
                    "trip": public_item(trip),
                }
            return None

        day_count = int(trip["day_count"])
        next_day_index = day_index + 1
        new_status = "complete" if next_day_index > day_count else "planning"
        visited, summary = self._cursors_from_existing_day(
            trip=trip,
            day_item=existing,
            next_index=day_index,
            fallback_visited=list(trip.get("visited_place_keys") or []),
            fallback_summary=str(trip.get("prior_days_summary") or ""),
        )
        try:
            repo.complete_planning_after_day_write(
                user_sub=user_sub,
                trip_id=trip_id,
                planned_day_index=day_index,
                next_day_index=next_day_index,
                visited_place_keys=visited,
                prior_days_summary=summary,
                new_status=new_status,
                table=self._table,
            )
        except repo.ConcurrentModificationError as exc:
            trip_out = self._require_trip(user_sub, trip_id)
            if int(trip_out.get("next_day_index") or 0) > day_index:
                return {
                    "async": False,
                    "day": public_item(existing),
                    "trip": public_item(trip_out),
                }
            raise ApiError(409, str(exc), code="conflict") from exc

        trip_out = self._require_trip(user_sub, trip_id)
        return {
            "async": False,
            "day": public_item(existing),
            "trip": public_item(trip_out),
        }

    def _plan_next_day_sync(self, user_sub: str, trip_id: str) -> dict[str, Any]:
        trip, route, days = self._load_owned_bundle(user_sub, trip_id)
        status = trip.get("status")
        if status not in {"routing_confirmed", "planning", "failed"}:
            raise ApiError(
                409, f"cannot plan day from status={status!r}", code="bad_status"
            )

        if trip["destination_type"] != "city":
            if not route or route.get("status") != "confirmed":
                raise ApiError(409, "confirmed city route required", code="route_required")

        next_index = resolve_plan_day_index(trip=trip, days=days)
        stored_next = int(trip.get("next_day_index") or 1)
        if stored_next != next_index:
            trip = repo.update_trip(
                user_sub=user_sub,
                trip_id=trip_id,
                updates={"next_day_index": next_index},
                table=self._table,
            )

        return self._run_plan_day_and_persist(
            user_sub=user_sub,
            trip_id=trip_id,
            trip=trip,
            route=route,
            next_index=next_index,
            async_claimed=False,
            rollback_status=str(status),
        )

    def _run_plan_day_and_persist(
        self,
        *,
        user_sub: str,
        trip_id: str,
        trip: dict[str, Any],
        route: dict[str, Any] | None,
        next_index: int,
        async_claimed: bool,
        rollback_status: str = "planning",
    ) -> dict[str, Any]:
        day_count = int(trip["day_count"])
        start = parse_iso_date(str(trip["start_date"]), field="start_date")
        day_date = date_for_day_index(start, next_index)
        overnight = overnight_city_for_day(route, next_index, str(trip["destination"]))

        self.safety.check_text(str(trip.get("preferences") or ""), source="preferences")

        profile = ProfileService(table=self._table, safety=self.safety).get_profile(
            user_sub
        )
        energy_level = clamp_energy_level(profile.get("energy_level"))
        max_minutes = max_minutes_for_energy(energy_level)
        interests = [str(i) for i in (profile.get("interests") or []) if str(i).strip()]
        include_breakfast = bool(profile.get("suggest_include_breakfast"))
        merged_prefs = _merge_preferences(
            str(trip.get("preferences") or ""),
            str(profile.get("preferences") or ""),
            interests,
        )
        meal_line = _meal_guidance(include_breakfast=include_breakfast)
        if meal_line not in merged_prefs:
            merged_prefs = (
                f"{merged_prefs} | {meal_line}".strip(" |")
                if merged_prefs
                else meal_line
            )
        self.safety.check_text(merged_prefs, source="preferences")

        visited = list(trip.get("visited_place_keys") or [])
        for key in _profile_visited_keys(list(profile.get("visited_places") or [])):
            if key not in visited:
                visited.append(key)

        route_for_crew = _route_payload(route) if route else {}
        inputs = slim_crew_inputs(
            {
                "origin": trip["origin"],
                "destination": trip["destination"],
                "destination_type": trip["destination_type"],
                "day_index": str(next_index),
                "date": day_date.isoformat(),
                "overnight_city": overnight,
                "preferences": merged_prefs,
                "include_breakfast": "true" if include_breakfast else "false",
                "energy_level": str(energy_level),
                "max_comfortable_minutes": str(max_minutes),
                "interests": ", ".join(interests),
                "already_visited": ",".join(visited),
                "prior_days_summary": trip.get("prior_days_summary") or "",
                "city_route_json": (
                    json.dumps(_json_safe(route_for_crew)) if route_for_crew else ""
                ),
            },
            overnight_city=overnight,
            day_index=next_index,
        )
        day_data = self.runner.plan_day(inputs)
        places = list(day_data.get("places") or [])
        filtered = dedupe_places(places, visited)
        if len(filtered) < 1:
            raise ApiError(
                422,
                "all suggested places were already visited; retry plan-next-day",
                code="dedupe_empty",
            )
        filtered = enrich_places(
            filtered,
            overnight_city=overnight,
        )
        filtered = filter_quality_places(
            filtered,
            plan_date=day_date,
            max_comfortable_minutes=max_minutes,
            profile_visited_names=profile_visited_name_keys(
                list(profile.get("visited_places") or [])
            ),
        )
        day_data = {
            **day_data,
            "day_index": next_index,
            "date": day_date.isoformat(),
            "overnight_city": overnight,
            "places": filtered,
        }

        trip_visited = list(trip.get("visited_place_keys") or [])
        new_keys = [str(p.get("place_key")) for p in filtered if p.get("place_key")]
        updated_visited = trip_visited + [k for k in new_keys if k not in trip_visited]
        theme = str(day_data.get("theme") or f"Day {next_index}")
        prior = str(trip.get("prior_days_summary") or "").strip()
        line = f"Day {next_index}: {theme} @ {overnight}"
        prior_summary = f"{prior}\n{line}".strip() if prior else line

        next_day_index = next_index + 1
        new_status = "complete" if next_day_index > day_count else "planning"

        try:
            if async_claimed:
                day_item = self._persist_async_planned_day(
                    user_sub=user_sub,
                    trip_id=trip_id,
                    trip=trip,
                    day_data=day_data,
                    next_index=next_index,
                    next_day_index=next_day_index,
                    updated_visited=updated_visited,
                    prior_summary=prior_summary,
                    new_status=new_status,
                )
            else:
                day_item = repo.persist_planned_day(
                    user_sub=user_sub,
                    trip_id=trip_id,
                    day=day_data,
                    expected_next_day_index=next_index,
                    visited_place_keys=updated_visited,
                    prior_days_summary=prior_summary,
                    new_status=new_status,
                    rollback_status=rollback_status,
                    table=self._table,
                )
        except repo.ConcurrentModificationError as exc:
            raise ApiError(409, str(exc), code="conflict") from exc

        trip_out = self._require_trip(user_sub, trip_id)
        return {
            "async": False,
            "day": public_item(day_item),
            "trip": public_item(trip_out),
        }

    def _persist_async_planned_day(
        self,
        *,
        user_sub: str,
        trip_id: str,
        trip: dict[str, Any],
        day_data: dict[str, Any],
        next_index: int,
        next_day_index: int,
        updated_visited: list[str],
        prior_summary: str,
        new_status: str,
    ) -> dict[str, Any]:
        """Put DAY then clear claim; idempotent if DAY already exists."""
        live = repo.get_trip_meta(
            user_sub=user_sub, trip_id=trip_id, table=self._table
        )
        if not live:
            raise ApiError(404, "trip not found", code="not_found")
        if str(live.get("status") or "") == "deleting":
            raise ApiError(409, "trip is being deleted", code="trip_deleting")
        try:
            claimed_i = int(live.get("planning_day_index"))
        except (TypeError, ValueError):
            claimed_i = None
        if claimed_i != next_index:
            raise ApiError(
                409,
                "planning claim lost before day write",
                code="claim_mismatch",
            )

        existing = repo.get_day(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=next_index,
            table=self._table,
        )
        if existing is not None:
            day_item = existing
            visited, summary = self._cursors_from_existing_day(
                trip=live,
                day_item=existing,
                next_index=next_index,
                fallback_visited=updated_visited,
                fallback_summary=prior_summary,
            )
        else:
            try:
                day_item = repo.put_day_if_absent(
                    user_sub=user_sub,
                    trip_id=trip_id,
                    day=day_data,
                    table=self._table,
                )
                visited, summary = updated_visited, prior_summary
            except repo.ConcurrentModificationError:
                # Another writer finished the Put; complete the claim from that DAY.
                day_item = repo.get_day(
                    user_sub=user_sub,
                    trip_id=trip_id,
                    day_index=next_index,
                    table=self._table,
                )
                if day_item is None:
                    raise
                visited, summary = self._cursors_from_existing_day(
                    trip=live,
                    day_item=day_item,
                    next_index=next_index,
                    fallback_visited=updated_visited,
                    fallback_summary=prior_summary,
                )

        repo.complete_planning_after_day_write(
            user_sub=user_sub,
            trip_id=trip_id,
            planned_day_index=next_index,
            next_day_index=next_day_index,
            visited_place_keys=visited,
            prior_days_summary=summary,
            new_status=new_status,
            table=self._table,
        )
        return day_item

    @staticmethod
    def _cursors_from_existing_day(
        *,
        trip: dict[str, Any],
        day_item: dict[str, Any],
        next_index: int,
        fallback_visited: list[str],
        fallback_summary: str,
    ) -> tuple[list[str], str]:
        trip_visited = list(trip.get("visited_place_keys") or [])
        places = list(day_item.get("places") or [])
        new_keys = [str(p.get("place_key")) for p in places if p.get("place_key")]
        if new_keys:
            visited = trip_visited + [k for k in new_keys if k not in trip_visited]
        else:
            visited = fallback_visited
        theme = str(day_item.get("theme") or f"Day {next_index}")
        overnight = str(day_item.get("overnight_city") or "")
        prior = str(trip.get("prior_days_summary") or "").strip()
        line = f"Day {next_index}: {theme} @ {overnight}".strip()
        if line.endswith("@"):
            line = line[:-1].strip()
        summary = f"{prior}\n{line}".strip() if prior else line
        return visited, summary or fallback_summary

    def suggest_place(
        self, user_sub: str, trip_id: str, day_index: int
    ) -> dict[str, Any]:
        """Research and append one place to an existing planned day."""
        if day_index < 1:
            raise ApiError(400, "day_index must be >= 1", code="invalid_day_index")

        trip = self._require_trip(user_sub, trip_id)
        day_count = int(trip.get("day_count") or 0)
        if day_count and day_index > day_count:
            raise ApiError(
                400,
                f"day_index {day_index} is outside trip window 1..{day_count}",
                code="invalid_day_index",
            )
        day = repo.get_day(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            table=self._table,
        )
        if not day:
            raise ApiError(404, "day not found", code="not_found")

        existing = list(day.get("places") or [])
        if len(existing) >= 6:
            raise ApiError(422, "day already has the maximum of 6 places", code="day_full")

        start = parse_iso_date(str(trip["start_date"]), field="start_date")
        raw_date = str(day.get("date") or "").strip()
        if raw_date:
            day_date = parse_iso_date(raw_date[:10], field="date")
        else:
            day_date = date_for_day_index(start, day_index)
        overnight = str(day.get("overnight_city") or trip["destination"])

        profile = ProfileService(table=self._table, safety=self.safety).get_profile(
            user_sub
        )
        energy_level = clamp_energy_level(profile.get("energy_level"))
        max_minutes = max_minutes_for_energy(energy_level)
        interests = [str(i) for i in (profile.get("interests") or []) if str(i).strip()]
        merged_prefs = _merge_preferences(
            str(trip.get("preferences") or ""),
            str(profile.get("preferences") or ""),
            interests,
        )
        self.safety.check_text(merged_prefs, source="preferences")

        current_total = day_total_minutes(existing)
        remaining = max_minutes - current_total
        if remaining < 1:
            raise ApiError(
                422,
                f"day already at or over energy warning threshold "
                f"({current_total} >= {max_minutes} minutes)",
                code="energy_overload",
            )

        visited = list(trip.get("visited_place_keys") or [])
        for key in _profile_visited_keys(list(profile.get("visited_places") or [])):
            if key not in visited:
                visited.append(key)
        for place in existing:
            key = str(place.get("place_key") or "").strip()
            if key and key not in visited:
                visited.append(key)

        slim_current = [
            {
                "name": p.get("name"),
                "place_key": p.get("place_key"),
                "category": p.get("category"),
                "estimated_minutes": p.get("estimated_minutes"),
            }
            for p in existing
        ]
        inputs = slim_crew_inputs(
            {
                "overnight_city": overnight,
                "day_index": str(day_index),
                "date": day_date.isoformat(),
                "preferences": merged_prefs,
                "interests": ", ".join(interests),
                "energy_level": str(energy_level),
                "remaining_minutes": str(remaining),
                "already_visited": ",".join(visited),
                "current_places_json": json.dumps(_json_safe(slim_current)),
                "next_order_in_day": str(len(existing) + 1),
            },
            overnight_city=overnight,
            day_index=day_index,
        )
        raw = self.runner.suggest_place(inputs)
        if (
            isinstance(raw, dict)
            and "error" in raw
            and "code" in raw
            and "place_key" not in raw
        ):
            code = str(raw.get("code") or "crew_failed")
            status = 400 if code in {"invalid_payload", "invalid_crew"} else 502
            detail = str(raw.get("error") or "suggest_place failed")
            raise ApiError(
                status,
                client_facing_message(status_code=status, code=code, detail=detail),
                code=code,
            )
        candidate = raw.get("place") if isinstance(raw.get("place"), dict) else raw
        if not isinstance(candidate, dict):
            raise ApiError(422, "crew did not return a place", code="invalid_place")

        candidate = enrich_place(
            candidate,
            overnight_city=overnight,
        )
        validated = validate_suggested_place(
            candidate,
            existing_places=existing,
            plan_date=day_date,
            max_comfortable_minutes=max_minutes,
            already_visited_keys=set(visited),
            profile_visited_names=profile_visited_name_keys(
                list(profile.get("visited_places") or [])
            ),
        )
        updated_places = [*existing, validated]
        place_key = str(validated.get("place_key") or "")
        trip_visited = list(trip.get("visited_place_keys") or [])
        try:
            day_item, trip = repo.persist_suggested_place(
                user_sub=user_sub,
                trip_id=trip_id,
                day_index=day_index,
                places=updated_places,
                expected_place_count=len(existing),
                place_key=place_key,
                previous_visited_keys=trip_visited,
                table=self._table,
            )
        except repo.ConcurrentModificationError as exc:
            raise ApiError(409, str(exc), code="conflict") from exc
        except repo.PersistenceError as exc:
            raise ApiError(502, str(exc), code="persistence_error") from exc

        return {
            "place": validated,
            "day": public_item(day_item),
            "trip": public_item(trip),
        }

    def remove_place(
        self, user_sub: str, trip_id: str, day_index: int, place_index: int
    ) -> dict[str, Any]:
        """Remove one place from a day by list index and reindex order_in_day."""
        if day_index < 1:
            raise ApiError(400, "day_index must be >= 1", code="invalid_day_index")
        if place_index < 0:
            raise ApiError(400, "place_index must be >= 0", code="invalid_place_index")

        trip, _route, days = self._load_owned_bundle(user_sub, trip_id)
        if trip.get("planning_day_index") is not None:
            raise ApiError(
                409,
                "cannot edit places while planning is in progress",
                code="planning_in_progress",
            )
        if str(trip.get("status") or "") == "deleting":
            raise ApiError(409, "trip is being deleted", code="trip_deleting")

        day = next(
            (d for d in days if int(d.get("day_index") or 0) == day_index),
            None,
        )
        if not day:
            raise ApiError(404, "day not found", code="not_found")

        existing = list(day.get("places") or [])
        if place_index >= len(existing):
            raise ApiError(404, "place not found", code="not_found")

        removed = existing[place_index]
        removed_key = (
            str(removed.get("place_key") or "").strip()
            if isinstance(removed, dict)
            else ""
        )

        updated_places: list[dict[str, Any]] = []
        for index, place in enumerate(existing):
            if index == place_index:
                continue
            item = dict(place) if isinstance(place, dict) else {}
            item["order_in_day"] = len(updated_places) + 1
            updated_places.append(item)

        try:
            day_item = repo.replace_day_places(
                user_sub=user_sub,
                trip_id=trip_id,
                day_index=day_index,
                places=updated_places,
                expected_place_count=len(existing),
                table=self._table,
            )
        except repo.ConcurrentModificationError as exc:
            raise ApiError(409, str(exc), code="conflict") from exc

        remaining = [
            day_item if int(d.get("day_index") or 0) == day_index else d for d in days
        ]
        still_used = False
        if removed_key:
            for other in remaining:
                for place in other.get("places") or []:
                    if not isinstance(place, dict):
                        continue
                    if str(place.get("place_key") or "").strip() == removed_key:
                        still_used = True
                        break
                if still_used:
                    break

        trip_out = trip
        if removed_key and not still_used:
            try:
                trip_out = repo.prune_visited_place_keys(
                    user_sub=user_sub,
                    trip_id=trip_id,
                    keys_to_remove={removed_key},
                    table=self._table,
                )
            except repo.ConcurrentModificationError:
                # Place already removed; visited may be slightly stale — do not 409.
                trip_out = (
                    repo.get_trip_meta(
                        user_sub=user_sub, trip_id=trip_id, table=self._table
                    )
                    or trip
                )
        else:
            trip_out = (
                repo.get_trip_meta(
                    user_sub=user_sub, trip_id=trip_id, table=self._table
                )
                or trip
            )

        return {
            "day": public_item(day_item),
            "trip": public_item(trip_out),
        }

    def delete_day(
        self, user_sub: str, trip_id: str, day_index: int
    ) -> dict[str, Any]:
        """Delete an entire day plan and rewind planning cursors for gaps."""
        if day_index < 1:
            raise ApiError(400, "day_index must be >= 1", code="invalid_day_index")

        trip, _route, days = self._load_owned_bundle(user_sub, trip_id)
        if not any(int(d.get("day_index") or 0) == day_index for d in days):
            raise ApiError(404, "day not found", code="not_found")

        if trip.get("planning_day_index") is not None:
            raise ApiError(
                409,
                "cannot delete a day while planning is in progress",
                code="planning_in_progress",
            )
        if str(trip.get("status") or "") == "deleting":
            raise ApiError(409, "trip is being deleted", code="trip_deleting")

        deleted = next(
            (d for d in days if int(d.get("day_index") or 0) == day_index),
            None,
        )
        deleted_keys = {
            str(p.get("place_key") or "").strip()
            for p in (deleted.get("places") or [] if deleted else [])
            if isinstance(p, dict) and str(p.get("place_key") or "").strip()
        }

        remaining = [d for d in days if int(d.get("day_index") or 0) != day_index]
        still_used = {
            str(p.get("place_key") or "").strip()
            for d in remaining
            for p in (d.get("places") or [])
            if isinstance(p, dict) and str(p.get("place_key") or "").strip()
        }
        keys_to_prune = deleted_keys - still_used

        day_count = int(trip.get("day_count") or 0)
        next_day_index, new_status = status_after_day_edit(
            remaining_days=remaining,
            day_count=day_count,
            previous_status=str(trip.get("status") or ""),
        )
        prior_summary = rebuild_prior_days_summary(remaining)

        # Cursor update first (fails if a claim appears) — then delete the DAY row.
        try:
            trip = repo.apply_itinerary_edit(
                user_sub=user_sub,
                trip_id=trip_id,
                next_day_index=next_day_index,
                status=new_status,
                prior_days_summary=prior_summary,
                table=self._table,
            )
        except repo.ConcurrentModificationError as exc:
            raise ApiError(409, str(exc), code="conflict") from exc

        if not repo.delete_day(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            table=self._table,
        ):
            # Cursors already reflect the gap; treat as idempotent success.
            pass

        if keys_to_prune:
            try:
                trip = repo.prune_visited_place_keys(
                    user_sub=user_sub,
                    trip_id=trip_id,
                    keys_to_remove=keys_to_prune,
                    table=self._table,
                )
            except repo.ConcurrentModificationError:
                trip = (
                    repo.get_trip_meta(
                        user_sub=user_sub, trip_id=trip_id, table=self._table
                    )
                    or trip
                )

        return {
            "deleted_day_index": day_index,
            "trip": public_item(trip),
            "days": [public_item(d) for d in remaining],
        }

    def _require_trip(self, user_sub: str, trip_id: str) -> dict[str, Any]:
        trip = repo.get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=self._table)
        if not trip:
            raise ApiError(404, "trip not found", code="not_found")
        return trip

    def _load_owned_bundle(
        self, user_sub: str, trip_id: str
    ) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
        items = repo.get_trip_bundle(user_sub=user_sub, trip_id=trip_id, table=self._table)
        trip, route, days = _split_bundle(items)
        if not trip:
            raise ApiError(404, "trip not found", code="not_found")
        if trip.get("user_id") and trip["user_id"] != user_sub:
            raise ApiError(403, "forbidden", code="forbidden")
        return trip, route, days
