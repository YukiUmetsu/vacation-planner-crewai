"""Trip HTTP routes."""

from __future__ import annotations

from typing import Any

from crews.runner import CrewRunner
from db.protocols import DynamoDBTable
from http_utils import parse_body
from services.safety import SafetyGate
from services.trip_service import TripService


def _service(
    *,
    table: DynamoDBTable | None = None,
    runner: CrewRunner | None = None,
    safety: SafetyGate | None = None,
) -> TripService:
    return TripService(table=table, runner=runner, safety=safety)


def create_trip(event: dict[str, Any], user_sub: str, **kwargs: Any) -> dict[str, Any]:
    return _service(**kwargs).create_trip(user_sub, parse_body(event))


def list_trips(event: dict[str, Any], user_sub: str, **kwargs: Any) -> dict[str, Any]:
    return _service(**kwargs).list_trips(user_sub)


def get_trip(event: dict[str, Any], user_sub: str, trip_id: str, **kwargs: Any) -> dict[str, Any]:
    return _service(**kwargs).get_trip(user_sub, trip_id)


def update_trip(
    event: dict[str, Any], user_sub: str, trip_id: str, **kwargs: Any
) -> dict[str, Any]:
    return _service(**kwargs).update_trip(user_sub, trip_id, parse_body(event))


def delete_trip(
    event: dict[str, Any], user_sub: str, trip_id: str, **kwargs: Any
) -> dict[str, Any]:
    return _service(**kwargs).delete_trip(user_sub, trip_id)


def propose_cities(
    event: dict[str, Any], user_sub: str, trip_id: str, **kwargs: Any
) -> dict[str, Any]:
    return _service(**kwargs).propose_cities(user_sub, trip_id)


def confirm_cities(
    event: dict[str, Any], user_sub: str, trip_id: str, **kwargs: Any
) -> dict[str, Any]:
    return _service(**kwargs).confirm_cities(user_sub, trip_id, parse_body(event))


def plan_next_day(
    event: dict[str, Any], user_sub: str, trip_id: str, **kwargs: Any
) -> dict[str, Any]:
    return _service(**kwargs).plan_next_day(user_sub, trip_id)


def suggest_place(
    event: dict[str, Any],
    user_sub: str,
    trip_id: str,
    day_index: int,
    **kwargs: Any,
) -> dict[str, Any]:
    return _service(**kwargs).suggest_place(user_sub, trip_id, day_index)


def remove_place(
    event: dict[str, Any],
    user_sub: str,
    trip_id: str,
    day_index: int,
    place_index: int,
    **kwargs: Any,
) -> dict[str, Any]:
    return _service(**kwargs).remove_place(
        user_sub, trip_id, day_index, place_index
    )


def delete_day(
    event: dict[str, Any],
    user_sub: str,
    trip_id: str,
    day_index: int,
    **kwargs: Any,
) -> dict[str, Any]:
    return _service(**kwargs).delete_day(user_sub, trip_id, day_index)
