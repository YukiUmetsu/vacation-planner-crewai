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
