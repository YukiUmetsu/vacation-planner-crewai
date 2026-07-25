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
from http_utils import ApiError, public_item
from models.api import ConfirmCitiesRequest
from crew_io.envelope import unwrap_crew_payload
from safety.gate import SafetyGate
from shared.route_windows import normalize_route_windows
from ops.worker_observability import WorkerTimer, log_crew_duration


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
) -> dict[str, Any]:
    from limits.genai import consume_genai_action
    from user_profile.service import ProfileService

    destination_type = trip["destination_type"]
    if destination_type == "city":
        raise ApiError(409, "city destinations skip propose-cities", code="not_applicable")

    status = trip.get("status")
    if status not in {"drafting", "awaiting_city_confirm"}:
        raise ApiError(409, f"cannot propose cities from status={status!r}", code="bad_status")

    profile = ProfileService(table=table, safety=safety).get_profile(
        user_sub, email=email
    )
    # Pre-crew gates first: safety rejection must not consume GenAI quota.
    safety.check_text(str(trip.get("preferences") or ""), source="preferences")
    safety.check_text(str(trip.get("destination") or ""), source="destination")
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
    trip_out = repo.update_trip(
        user_sub=user_sub,
        trip_id=trip_id,
        updates={"status": "awaiting_city_confirm"},
        table=table,
    )
    return {"trip": public_item(trip_out), "route": public_item(route)}


def confirm_cities(
    *,
    user_sub: str,
    trip_id: str,
    trip: dict[str, Any],
    req: ConfirmCitiesRequest,
    table: DynamoDBTable | None,
) -> dict[str, Any]:
    status = trip.get("status")
    if status not in {"awaiting_city_confirm", "drafting", "routing_confirmed"}:
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

    route = repo.put_route(
        user_sub=user_sub,
        trip_id=trip_id,
        route=route_data,
        table=table,
    )
    trip_out = repo.update_trip(
        user_sub=user_sub,
        trip_id=trip_id,
        updates={"status": "routing_confirmed"},
        table=table,
    )
    return {"trip": public_item(trip_out), "route": public_item(route)}
