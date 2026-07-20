"""Minimal single-table persistence for trips / routes / days."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from db import keys
from db.client import get_table
from db.schema import GSI1_NAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def put_trip(
    *,
    user_sub: str,
    trip_id: str,
    origin: str,
    destination: str,
    destination_type: str,
    start_date: str,
    end_date: str,
    day_count: int,
    preferences: str = "",
    status: str = "drafting",
    table: Any | None = None,
) -> dict[str, Any]:
    tbl = table or get_table()
    item = {
        "pk": keys.user_pk(user_sub),
        "sk": keys.trip_sk(trip_id),
        "gsi1pk": keys.gsi1_pk(trip_id),
        "gsi1sk": keys.gsi1_sk_user(user_sub),
        "entity_type": "TRIP",
        "trip_id": trip_id,
        "user_id": user_sub,
        "origin": origin,
        "destination": destination,
        "destination_type": destination_type,
        "start_date": start_date,
        "end_date": end_date,
        "day_count": day_count,
        "next_day_index": 1,
        "status": status,
        "preferences": preferences,
        "visited_place_keys": [],
        "prior_days_summary": "",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    tbl.put_item(Item=item)
    return item


def put_route(
    *,
    user_sub: str,
    trip_id: str,
    route: dict[str, Any],
    table: Any | None = None,
) -> dict[str, Any]:
    tbl = table or get_table()
    item = {
        "pk": keys.user_pk(user_sub),
        "sk": keys.route_sk(trip_id),
        "gsi1pk": keys.gsi1_pk(trip_id),
        "gsi1sk": keys.gsi1_sk_route(),
        "entity_type": "ROUTE",
        "trip_id": trip_id,
        **route,
        "updated_at": _now_iso(),
    }
    tbl.put_item(Item=item)
    return item


def put_day(
    *,
    user_sub: str,
    trip_id: str,
    day: dict[str, Any],
    table: Any | None = None,
) -> dict[str, Any]:
    tbl = table or get_table()
    day_index = int(day["day_index"])
    item = {
        "pk": keys.user_pk(user_sub),
        "sk": keys.day_sk(trip_id, day_index),
        "gsi1pk": keys.gsi1_pk(trip_id),
        "gsi1sk": keys.gsi1_sk_day(day_index),
        "entity_type": "DAY",
        "trip_id": trip_id,
        **day,
        "created_at": _now_iso(),
    }
    tbl.put_item(Item=item)
    return item


def list_trip_meta_for_user(*, user_sub: str, table: Any | None = None) -> list[dict[str, Any]]:
    """List TRIP meta rows only (exclude ROUTE/DAY)."""
    tbl = table or get_table()
    response = tbl.query(
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={
            ":pk": keys.user_pk(user_sub),
            ":prefix": "TRIP#",
            ":etype": "TRIP",
        },
        FilterExpression="entity_type = :etype",
    )
    return response.get("Items", [])


def get_trip_bundle(*, user_sub: str, trip_id: str, table: Any | None = None) -> list[dict[str, Any]]:
    """Trip meta + route + days for one trip (same partition prefix)."""
    tbl = table or get_table()
    response = tbl.query(
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={
            ":pk": keys.user_pk(user_sub),
            ":prefix": keys.trip_sk(trip_id),
        },
    )
    return response.get("Items", [])


def get_trip_by_id_via_gsi(*, trip_id: str, table: Any | None = None) -> list[dict[str, Any]]:
    """Lookup by trip_id using GSI1 (still authorize with user_sub in the API layer)."""
    tbl = table or get_table()
    response = tbl.query(
        IndexName=GSI1_NAME,
        KeyConditionExpression="gsi1pk = :gpk",
        ExpressionAttributeValues={":gpk": keys.gsi1_pk(trip_id)},
    )
    return response.get("Items", [])
