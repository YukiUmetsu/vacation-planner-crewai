"""Trip CRUD (create/update/list/get/delete) and bundle-loading helpers.

Per ADR 005: takes `table` as an explicit arg and must never import
`trips.service.TripService`. May import `trips.city_route` (one-way — the
route module does not import this one back).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from db import repository as repo
from db.protocols import DynamoDBTable
from http_utils import ApiError, public_item
from models.api import CreateTripRequest, UpdateTripRequest
from safety.gate import SafetyGate, check_texts
from shared.dates import validate_trip_dates

from trips.city_route import synthetic_city_route


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


def _require_trip(*, user_sub: str, trip_id: str, table: DynamoDBTable | None) -> dict[str, Any]:
    trip = repo.get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=table)
    if not trip:
        raise ApiError(404, "trip not found", code="not_found")
    return trip


def _load_owned_bundle(
    *, user_sub: str, trip_id: str, table: DynamoDBTable | None
) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
    items = repo.get_trip_bundle(user_sub=user_sub, trip_id=trip_id, table=table)
    trip, route, days = _split_bundle(items)
    if not trip:
        raise ApiError(404, "trip not found", code="not_found")
    if trip.get("user_id") and trip["user_id"] != user_sub:
        raise ApiError(403, "forbidden", code="forbidden")
    return trip, route, days


def create_trip(
    *,
    user_sub: str,
    body: dict[str, Any],
    table: DynamoDBTable | None,
    safety: SafetyGate,
    email: str | None = None,
) -> dict[str, Any]:
    from limits.trips import assert_can_create_trip
    from user_profile.service import ProfileService

    profile = ProfileService(table=table, safety=safety).get_profile(
        user_sub, email=email
    )
    existing = repo.list_trip_meta_for_user(user_sub=user_sub, table=table)
    assert_can_create_trip(
        user_sub=user_sub,
        trip_count=len(existing),
        profile=profile,
        email=email,
    )

    req = _validate(CreateTripRequest, body)
    start, end, day_count = validate_trip_dates(req.start_date, req.end_date)
    check_texts(
        safety,
        {
            "preferences": req.preferences,
            "destination": req.destination,
            "origin": req.origin,
        },
    )

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
        table=table,
    )

    route = None
    if req.destination_type == "city":
        route = repo.put_route(
            user_sub=user_sub,
            trip_id=trip_id,
            route=synthetic_city_route(destination=req.destination, day_count=day_count),
            table=table,
        )

    return {
        "trip": public_item(trip),
        "route": public_item(route) if route else None,
    }


def update_trip(
    *,
    user_sub: str,
    trip_id: str,
    body: dict[str, Any],
    table: DynamoDBTable | None,
    safety: SafetyGate,
) -> dict[str, Any]:
    """Update trip details; clears the route so cities can be re-proposed."""
    trip, route, days = _load_owned_bundle(user_sub=user_sub, trip_id=trip_id, table=table)
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

    check_texts(
        safety,
        {
            "preferences": preferences,
            "destination": destination,
            "origin": origin,
        },
        trip_id=trip_id,
    )
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
    repo.delete_route(user_sub=user_sub, trip_id=trip_id, table=table)
    if destination_type == "city":
        updates["status"] = "routing_confirmed"
        route = repo.put_route(
            user_sub=user_sub,
            trip_id=trip_id,
            route=synthetic_city_route(
                destination=destination, day_count=day_count
            ),
            table=table,
        )
    else:
        updates["status"] = "drafting"
        route = None

    trip = repo.update_trip(
        user_sub=user_sub,
        trip_id=trip_id,
        updates=updates,
        table=table,
    )
    return {
        "trip": public_item(trip),
        "route": public_item(route) if route else None,
    }


def list_trips(*, user_sub: str, table: DynamoDBTable | None) -> dict[str, Any]:
    items = repo.list_trip_meta_for_user(user_sub=user_sub, table=table)
    items_sorted = sorted(items, key=lambda t: t.get("created_at") or "", reverse=True)
    return {"trips": [public_item(t) for t in items_sorted]}


def get_trip(*, user_sub: str, trip_id: str, table: DynamoDBTable | None) -> dict[str, Any]:
    trip, route, days = _load_owned_bundle(user_sub=user_sub, trip_id=trip_id, table=table)
    return {
        "trip": public_item(trip),
        "route": public_item(route) if route else None,
        "days": [public_item(d) for d in days],
    }


def delete_trip(*, user_sub: str, trip_id: str, table: DynamoDBTable | None) -> dict[str, Any]:
    """Remove trip meta, route, and all day-plan rows for an owned trip."""
    _require_trip(user_sub=user_sub, trip_id=trip_id, table=table)
    try:
        # Atomic delete lock: fails if a planning claim is held.
        repo.begin_trip_delete(user_sub=user_sub, trip_id=trip_id, table=table)
    except repo.ConcurrentModificationError as exc:
        raise ApiError(
            409,
            "cannot delete trip while planning is in progress",
            code="planning_in_progress",
        ) from exc
    counts = repo.delete_trip_bundle(user_sub=user_sub, trip_id=trip_id, table=table)
    return {"ok": True, "trip_id": trip_id, "deleted": counts}
