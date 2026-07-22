"""Trip orchestration: create, route confirm, plan-next-day."""

from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic import ValidationError

from crews.runner import CrewRunner, get_crew_runner
from db import repository as repo
from db.protocols import DynamoDBTable
from http_utils import ApiError, public_item
from models.api import ConfirmCitiesRequest, CreateTripRequest
from services.crew_context_budget import slim_crew_inputs
from services.dates import date_for_day_index, parse_iso_date, validate_trip_dates
from services.dedupe import dedupe_places
from services.energy import clamp_energy_level, max_minutes_for_energy
from services.place_quality import (
    day_total_minutes,
    filter_quality_places,
    profile_visited_name_keys,
    validate_suggested_place,
)
from services.places_enrich import enrich_place, enrich_places
from services.profile_service import ProfileService
from services.safety import SafetyGate, get_safety_gate
from db.place_keys import make_place_key
from decimal import Decimal


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
        raise ApiError(400, "route.cities must be non-empty")
    covered: set[int] = set()
    for stop in cities:
        arrival = int(stop.get("arrival_day_index") or 0)
        departure = int(stop.get("departure_day_index") or 0)
        if not (1 <= arrival <= day_count and 1 <= departure <= day_count):
            raise ApiError(400, "city day indices must fall within the trip window")
        if departure < arrival:
            raise ApiError(400, "departure_day_index must be >= arrival_day_index")
        for day in range(arrival, departure + 1):
            if day in covered:
                raise ApiError(
                    400,
                    f"route has overlapping city coverage on day {day}",
                    code="route_overlap",
                )
            covered.add(day)
    nights_sum = sum(int(c.get("nights") or 0) for c in cities)
    total = int(route.get("total_nights") or nights_sum)
    if total != nights_sum:
        raise ApiError(400, f"total_nights ({total}) must equal sum of city nights ({nights_sum})")
    expected_nights = max(0, day_count - 1)
    if nights_sum != expected_nights:
        raise ApiError(
            400,
            f"sum of city nights ({nights_sum}) must equal day_count - 1 ({expected_nights})",
            code="route_nights_mismatch",
        )
    missing = [day for day in range(1, day_count + 1) if day not in covered]
    if missing:
        raise ApiError(
            400,
            f"route does not cover all trip days (missing {missing})",
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
    ) -> None:
        self._table = table
        self._runner = runner
        self._safety = safety

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

    def list_trips(self, user_sub: str) -> dict[str, Any]:
        items = repo.list_trip_meta_for_user(user_sub=user_sub, table=self._table)
        items_sorted = sorted(items, key=lambda t: t.get("created_at") or "", reverse=True)
        return {"trips": [public_item(t) for t in items_sorted]}

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
        route_data = _sync_total_nights(self.runner.propose_cities(inputs))
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
        trip, route, days = self._load_owned_bundle(user_sub, trip_id)
        status = trip.get("status")
        if status not in {"routing_confirmed", "planning"}:
            raise ApiError(409, f"cannot plan day from status={status!r}", code="bad_status")

        day_count = int(trip["day_count"])
        next_index = int(trip.get("next_day_index") or 1)
        if next_index > day_count:
            raise ApiError(409, "all days already planned", code="complete")

        if trip["destination_type"] != "city":
            if not route or route.get("status") != "confirmed":
                raise ApiError(409, "confirmed city route required", code="route_required")

        start = parse_iso_date(str(trip["start_date"]), field="start_date")
        day_date = date_for_day_index(start, next_index)
        overnight = overnight_city_for_day(route, next_index, str(trip["destination"]))

        self.safety.check_text(str(trip.get("preferences") or ""), source="preferences")

        profile = ProfileService(table=self._table, safety=self.safety).get_profile(user_sub)
        energy_level = clamp_energy_level(profile.get("energy_level"))
        max_minutes = max_minutes_for_energy(energy_level)
        interests = [str(i) for i in (profile.get("interests") or []) if str(i).strip()]
        merged_prefs = _merge_preferences(
            str(trip.get("preferences") or ""),
            str(profile.get("preferences") or ""),
            interests,
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
            day_item = repo.persist_planned_day(
                user_sub=user_sub,
                trip_id=trip_id,
                day=day_data,
                expected_next_day_index=next_index,
                visited_place_keys=updated_visited,
                prior_days_summary=prior_summary,
                new_status=new_status,
                rollback_status=str(status),
                table=self._table,
            )
        except repo.ConcurrentModificationError as exc:
            raise ApiError(409, str(exc), code="conflict") from exc

        trip = self._require_trip(user_sub, trip_id)
        return {
            "day": public_item(day_item),
            "trip": public_item(trip),
        }

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
            raise ApiError(
                502,
                str(raw.get("error") or "suggest_place failed"),
                code=str(raw.get("code") or "crew_failed"),
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
