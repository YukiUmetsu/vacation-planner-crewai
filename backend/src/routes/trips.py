"""Trip HTTP routes."""

from __future__ import annotations

from typing import Any

from auth import get_user_email
from crews.runner import CrewRunner
from db.protocols import DynamoDBTable
from http_utils import parse_body
from safety.gate import SafetyGate
from trips.service import TripService


def _service(
    *,
    table: DynamoDBTable | None = None,
    runner: CrewRunner | None = None,
    safety: SafetyGate | None = None,
) -> TripService:
    return TripService(table=table, runner=runner, safety=safety)


def create_trip(event: dict[str, Any], user_sub: str, **kwargs: Any) -> dict[str, Any]:
    return _service(**kwargs).create_trip(
        user_sub, parse_body(event), email=get_user_email(event)
    )


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
    return _service(**kwargs).propose_cities(
        user_sub, trip_id, email=get_user_email(event)
    )


def confirm_cities(
    event: dict[str, Any], user_sub: str, trip_id: str, **kwargs: Any
) -> dict[str, Any]:
    return _service(**kwargs).confirm_cities(user_sub, trip_id, parse_body(event))


def plan_next_day(
    event: dict[str, Any], user_sub: str, trip_id: str, **kwargs: Any
) -> dict[str, Any]:
    return _service(**kwargs).plan_next_day(
        user_sub, trip_id, email=get_user_email(event)
    )


def suggest_place(
    event: dict[str, Any],
    user_sub: str,
    trip_id: str,
    day_index: int,
    **kwargs: Any,
) -> dict[str, Any]:
    return _service(**kwargs).suggest_place(
        user_sub,
        trip_id,
        day_index,
        parse_body(event),
        email=get_user_email(event),
    )


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


def reorder_place(
    event: dict[str, Any],
    user_sub: str,
    trip_id: str,
    day_index: int,
    **kwargs: Any,
) -> dict[str, Any]:
    body = parse_body(event)
    try:
        from_index = int(body.get("from_index"))
        to_index = int(body.get("to_index"))
    except (TypeError, ValueError) as exc:
        from http_utils import ApiError

        raise ApiError(
            400,
            "from_index and to_index are required integers",
            code="invalid_place_index",
        ) from exc
    return _service(**kwargs).reorder_place(
        user_sub, trip_id, day_index, from_index, to_index
    )


def suggest_city(
    event: dict[str, Any], user_sub: str, trip_id: str, **kwargs: Any
) -> dict[str, Any]:
    return _service(**kwargs).suggest_city(
        user_sub, trip_id, parse_body(event), email=get_user_email(event)
    )


def delete_day(
    event: dict[str, Any],
    user_sub: str,
    trip_id: str,
    day_index: int,
    **kwargs: Any,
) -> dict[str, Any]:
    return _service(**kwargs).delete_day(user_sub, trip_id, day_index)
