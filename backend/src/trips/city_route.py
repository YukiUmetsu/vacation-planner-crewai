"""City-route propose/confirm, synthetic single-city routes, window validation.

Per ADR 005 (`docs/architecture-decisions/005-services-domain-packages.md`):
submodules take `table` / `runner` / `safety` as explicit args and must never
import `trips.service.TripService`.
"""

from __future__ import annotations

from typing import Any

from crews.runner import CrewRunner, crew_mode
from db import repository as repo
from db.protocols import DynamoDBTable
from http_utils import ApiError, client_facing_message, public_item
from models.api import ConfirmCitiesRequest
from crew_io.envelope import unwrap_crew_payload
from safety.gate import SafetyGate
from shared.route_windows import normalize_route_windows
from ops.worker_observability import WorkerTimer, log_crew_duration
from trips.route_reconfirm import remap_itinerary_for_route_reconfirm


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


def assert_route_fits_window(route: dict[str, Any], day_count: int) -> None:
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


# Kept for backwards compatibility — private name imported by legacy shims/tests
# (see ADR 005 watch-out #3: promote-and-alias instead of leaving `_`-imports
# reaching across packages).
_assert_route_fits_window = assert_route_fits_window


def overnight_city_for_day(route: dict[str, Any] | None, day_index: int, destination: str) -> str:
    if not route:
        return destination
    for stop in route.get("cities") or []:
        arrival = int(stop.get("arrival_day_index") or 0)
        departure = int(stop.get("departure_day_index") or 0)
        if arrival <= day_index <= departure:
            return str(stop.get("city") or destination)
    raise ApiError(409, f"no city covers day_index={day_index}", code="route_gap")


def propose_cities(
    *,
    user_sub: str,
    trip_id: str,
    trip: dict[str, Any],
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
    email: str | None = None,
    enqueue_crew_job: Any | None = None,
) -> dict[str, Any]:
    from ops.crew_async import llm_async_enabled

    if llm_async_enabled():
        return start_propose_cities(
            user_sub=user_sub,
            trip_id=trip_id,
            trip=trip,
            table=table,
            safety=safety,
            email=email,
            enqueue_crew_job=enqueue_crew_job,
        )
    return _propose_cities_sync(
        user_sub=user_sub,
        trip_id=trip_id,
        trip=trip,
        table=table,
        runner=runner,
        safety=safety,
        email=email,
        charge_genai=True,
    )


def start_propose_cities(
    *,
    user_sub: str,
    trip_id: str,
    trip: dict[str, Any],
    table: DynamoDBTable | None,
    safety: SafetyGate,
    email: str | None = None,
    enqueue_crew_job: Any | None = None,
) -> dict[str, Any]:
    """Claim + enqueue propose-cities worker; returns async response shape."""
    from limits.genai import consume_genai_action, refund_genai_action
    from ops.crew_job_worker import enqueue_crew_job_worker
    from user_profile.service import ProfileService

    destination_type = trip["destination_type"]
    if destination_type == "city":
        raise ApiError(409, "city destinations skip propose-cities", code="not_applicable")

    status = trip.get("status")
    if status not in {"drafting", "awaiting_city_confirm"}:
        raise ApiError(409, f"cannot propose cities from status={status!r}", code="bad_status")

    if trip.get("planning_day_index") is not None:
        raise ApiError(
            409,
            "cannot propose cities while day planning is in progress",
            code="planning_in_progress",
        )

    profile = ProfileService(table=table, safety=safety).get_profile(
        user_sub, email=email
    )
    safety.check_text(str(trip.get("preferences") or ""), source="preferences")
    safety.check_text(str(trip.get("destination") or ""), source="destination")

    try:
        claimed = repo.claim_crew_job(
            user_sub=user_sub,
            trip_id=trip_id,
            kind=repo.JOB_PROPOSE_CITIES,
            table=table,
        )
    except repo.ConcurrentModificationError as exc:
        raise ApiError(409, str(exc), code="conflict") from exc

    try:
        consume_genai_action(
            user_sub=user_sub, profile=profile, email=email, table=table
        )
    except Exception as exc:
        repo.fail_crew_job(
            user_sub=user_sub,
            trip_id=trip_id,
            expected_kind=repo.JOB_PROPOSE_CITIES,
            error_message=client_facing_message(
                status_code=getattr(exc, "status_code", 500),
                code=getattr(exc, "code", "internal_error"),
                detail=str(getattr(exc, "message", exc)),
            ),
            table=table,
        )
        raise

    enqueue = enqueue_crew_job or enqueue_crew_job_worker
    try:
        enqueue(
            {
                "worker": repo.JOB_PROPOSE_CITIES,
                "user_sub": user_sub,
                "trip_id": trip_id,
            }
        )
    except Exception as exc:
        refund_genai_action(
            user_sub=user_sub, profile=profile, email=email, table=table
        )
        repo.fail_crew_job(
            user_sub=user_sub,
            trip_id=trip_id,
            expected_kind=repo.JOB_PROPOSE_CITIES,
            error_message=client_facing_message(
                status_code=502,
                code="enqueue_failed",
                detail=f"failed to start propose-cities: {type(exc).__name__}",
            ),
            table=table,
        )
        raise ApiError(
            502,
            client_facing_message(
                status_code=502,
                code="enqueue_failed",
                detail="failed to start async propose-cities worker",
            ),
            code="enqueue_failed",
        ) from exc

    return {
        "async": True,
        "trip": public_item(claimed),
        "job": repo.JOB_PROPOSE_CITIES,
    }


def execute_propose_cities(
    *,
    user_sub: str,
    trip_id: str,
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
) -> dict[str, Any]:
    """Worker path: run propose-cities for an already-claimed trip."""
    from trips.crud import _require_trip

    trip = _require_trip(user_sub=user_sub, trip_id=trip_id, table=table)
    if trip.get("crew_job_kind") != repo.JOB_PROPOSE_CITIES:
        raise ApiError(409, "propose-cities job claim missing", code="conflict")
    try:
        return _propose_cities_sync(
            user_sub=user_sub,
            trip_id=trip_id,
            trip=trip,
            table=table,
            runner=runner,
            safety=safety,
            email=None,
            charge_genai=False,
            complete_job=True,
        )
    except ApiError as exc:
        # Retryable AgentCore transport: keep claim so Event retries can run.
        if not exc.retryable:
            repo.fail_crew_job(
                user_sub=user_sub,
                trip_id=trip_id,
                expected_kind=repo.JOB_PROPOSE_CITIES,
                error_message=client_facing_message(
                    status_code=exc.status_code,
                    code=exc.code or "crew_failed",
                    detail=exc.message,
                ),
                table=table,
            )
        raise
    except Exception as exc:
        repo.fail_crew_job(
            user_sub=user_sub,
            trip_id=trip_id,
            expected_kind=repo.JOB_PROPOSE_CITIES,
            error_message=client_facing_message(
                status_code=500,
                code="internal_error",
                detail=type(exc).__name__,
            ),
            table=table,
        )
        raise


def _propose_cities_sync(
    *,
    user_sub: str,
    trip_id: str,
    trip: dict[str, Any],
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
    email: str | None = None,
    charge_genai: bool = True,
    complete_job: bool = False,
) -> dict[str, Any]:
    from limits.genai import consume_genai_action
    from user_profile.service import ProfileService

    destination_type = trip["destination_type"]
    if destination_type == "city":
        raise ApiError(409, "city destinations skip propose-cities", code="not_applicable")

    status = trip.get("status")
    if status not in {"drafting", "awaiting_city_confirm"} and not complete_job:
        raise ApiError(409, f"cannot propose cities from status={status!r}", code="bad_status")

    profile = ProfileService(table=table, safety=safety).get_profile(
        user_sub, email=email
    )
    # Pre-crew gates first: safety rejection must not consume GenAI quota.
    safety.check_text(str(trip.get("preferences") or ""), source="preferences")
    safety.check_text(str(trip.get("destination") or ""), source="destination")
    if charge_genai:
        consume_genai_action(
            user_sub=user_sub, profile=profile, email=email, table=table
        )

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
    proposed_raw = runner.propose_cities(inputs)
    proposed, _, _ = unwrap_crew_payload(proposed_raw)
    route_data = normalize_route_windows(
        _sync_total_nights(proposed),
        int(trip["day_count"]),
    )
    log_crew_duration(
        operation="propose_cities",
        trip_id=trip_id,
        duration_ms=timer.duration_ms(),
        extra={"crew_mode": crew_mode()},
    )
    route_data["status"] = "proposed"
    assert_route_fits_window(route_data, int(trip["day_count"]))

    route = repo.put_route(
        user_sub=user_sub,
        trip_id=trip_id,
        route=route_data,
        table=table,
    )
    if complete_job:
        trip_out = repo.complete_crew_job(
            user_sub=user_sub,
            trip_id=trip_id,
            expected_kind=repo.JOB_PROPOSE_CITIES,
            extra_sets={"status": "awaiting_city_confirm"},
            table=table,
        )
    else:
        trip_out = repo.update_trip(
            user_sub=user_sub,
            trip_id=trip_id,
            updates={"status": "awaiting_city_confirm"},
            table=table,
        )
    return {"trip": public_item(trip_out), "route": public_item(route)}


_CONFIRMABLE_STATUSES = frozenset(
    {
        "awaiting_city_confirm",
        "drafting",
        "routing_confirmed",
        # Reconfirm after day planning started (suggest-city → edit → confirm).
        "planning",
        "failed",
        "complete",
    }
)


def confirm_cities(
    *,
    user_sub: str,
    trip_id: str,
    trip: dict[str, Any],
    req: ConfirmCitiesRequest,
    table: DynamoDBTable | None,
) -> dict[str, Any]:
    status = str(trip.get("status") or "")
    if status == "deleting":
        raise ApiError(409, "trip is being deleted", code="trip_deleting")
    if trip.get("crew_job_kind") is not None:
        raise ApiError(
            409,
            "cannot confirm cities while a GenAI job is in progress",
            code="crew_job_in_progress",
        )
    if status not in _CONFIRMABLE_STATUSES:
        raise ApiError(409, f"cannot confirm cities from status={status!r}", code="bad_status")

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
    assert_route_fits_window(route_data, int(trip["day_count"]))

    bundle = repo.get_trip_bundle(user_sub=user_sub, trip_id=trip_id, table=table)
    days = [i for i in bundle if i.get("entity_type") == "DAY"]
    needs_itinerary_remap = (
        bool(days)
        or status in {"planning", "failed", "complete"}
        or trip.get("planning_day_index") is not None
        or int(trip.get("next_day_index") or 1) > 1
        or bool(trip.get("visited_place_keys"))
    )

    # Remap (or status update) before persisting the new ROUTE so a remap
    # failure does not leave confirmed cities mismatched with old DAY rows.
    kept_days: list[dict[str, Any]] = []
    if needs_itinerary_remap:
        try:
            kept_days, trip_out = remap_itinerary_for_route_reconfirm(
                user_sub=user_sub,
                trip_id=trip_id,
                route=route_data,
                start_date=str(trip["start_date"]),
                day_count=int(trip["day_count"]),
                destination=str(trip.get("destination") or ""),
                previous_status=status,
                table=table,
            )
        except repo.ConcurrentModificationError as exc:
            raise ApiError(409, str(exc), code="conflict") from exc
        except repo.PersistenceError as exc:
            raise ApiError(502, str(exc), code="persistence_error") from exc
    else:
        trip_out = repo.update_trip(
            user_sub=user_sub,
            trip_id=trip_id,
            updates={"status": "routing_confirmed"},
            table=table,
        )

    route = repo.put_route(
        user_sub=user_sub,
        trip_id=trip_id,
        route=route_data,
        table=table,
    )

    return {
        "trip": public_item(trip_out),
        "route": public_item(route),
        "days": [public_item(d) for d in kept_days],
    }
