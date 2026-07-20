"""Minimal single-table persistence for trips / routes / days."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from db import keys
from db.client import get_table
from db.protocols import DynamoDBTable
from db.schema import GSI1_NAME

# DynamoDB item documents (keys + attributes). Numbers may be Decimal from boto3.
DynamoItem = dict[str, Any]


class ConcurrentModificationError(Exception):
    """Raised when a conditional DynamoDB write loses a race."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_nones(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return [_strip_nones(v) for v in value if v is not None]
    if isinstance(value, dict):
        return {k: _strip_nones(v) for k, v in value.items() if v is not None}
    return value


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
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    tbl = table or get_table()
    item: DynamoItem = {
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
    route: DynamoItem,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    tbl = table or get_table()
    item: DynamoItem = {
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
    day: DynamoItem,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    tbl = table or get_table()
    day_index = int(day["day_index"])
    item: DynamoItem = {
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


def list_trip_meta_for_user(
    *,
    user_sub: str,
    table: DynamoDBTable | None = None,
) -> list[DynamoItem]:
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
    return list(response.get("Items") or [])


def get_trip_bundle(
    *,
    user_sub: str,
    trip_id: str,
    table: DynamoDBTable | None = None,
) -> list[DynamoItem]:
    """Trip meta + route + days for one trip (same partition prefix)."""
    tbl = table or get_table()
    response = tbl.query(
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={
            ":pk": keys.user_pk(user_sub),
            ":prefix": keys.trip_sk(trip_id),
        },
    )
    return list(response.get("Items") or [])


def get_trip_by_id_via_gsi(
    *,
    trip_id: str,
    table: DynamoDBTable | None = None,
) -> list[DynamoItem]:
    """Lookup by trip_id using GSI1 (still authorize with user_sub in the API layer)."""
    tbl = table or get_table()
    response = tbl.query(
        IndexName=GSI1_NAME,
        KeyConditionExpression="gsi1pk = :gpk",
        ExpressionAttributeValues={":gpk": keys.gsi1_pk(trip_id)},
    )
    return list(response.get("Items") or [])


def get_trip_meta(
    *,
    user_sub: str,
    trip_id: str,
    table: DynamoDBTable | None = None,
) -> DynamoItem | None:
    """Fetch the single TRIP meta row by primary key (not route/days).

    ``Table.get_item(Key=...)`` is a point read: one item for exact pk+sk.
    Response shape: ``{"Item": {...}}`` if found, or ``{}`` if missing.
    """
    tbl = table or get_table()
    response = tbl.get_item(
        Key={"pk": keys.user_pk(user_sub), "sk": keys.trip_sk(trip_id)},
    )
    item = response.get("Item")
    if not item or item.get("entity_type") != "TRIP":
        return None
    return item


def update_trip(
    *,
    user_sub: str,
    trip_id: str,
    updates: DynamoItem,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    """Partial update of trip meta fields. Always refreshes updated_at."""
    tbl = table or get_table()
    payload: DynamoItem = {**updates, "updated_at": _now_iso()}
    names: dict[str, str] = {}
    values: DynamoItem = {}
    parts: list[str] = []
    for index, (field, value) in enumerate(payload.items()):
        name_key = f"#f{index}"
        value_key = f":v{index}"
        names[name_key] = field
        values[value_key] = value
        parts.append(f"{name_key} = {value_key}")

    response = tbl.update_item(
        Key={"pk": keys.user_pk(user_sub), "sk": keys.trip_sk(trip_id)},
        UpdateExpression="SET " + ", ".join(parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ConditionExpression="attribute_exists(pk)",
        ReturnValues="ALL_NEW",
    )
    return response["Attributes"]


def _is_conditional_failure(exc: BaseException) -> bool:
    response = getattr(exc, "response", {}) or {}
    code = (response.get("Error") or {}).get("Code", "")
    return code == "ConditionalCheckFailedException" or "ConditionalCheckFailed" in type(
        exc
    ).__name__


def claim_next_day_slot(
    *,
    user_sub: str,
    trip_id: str,
    expected_next_day_index: int,
    new_status: str,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    """Conditionally advance ``next_day_index`` (optimistic lock / claim).

    Losers of the race get ``ConcurrentModificationError`` before any DAY write.
    """
    tbl = table or get_table()
    try:
        response = tbl.update_item(
            Key={"pk": keys.user_pk(user_sub), "sk": keys.trip_sk(trip_id)},
            UpdateExpression="SET #ndi = :new_ndi, #st = :st, #ua = :ua",
            ExpressionAttributeNames={
                "#ndi": "next_day_index",
                "#st": "status",
                "#ua": "updated_at",
            },
            ExpressionAttributeValues={
                ":expected": expected_next_day_index,
                ":new_ndi": expected_next_day_index + 1,
                ":st": new_status,
                ":ua": _now_iso(),
            },
            ConditionExpression="next_day_index = :expected",
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if _is_conditional_failure(exc):
            raise ConcurrentModificationError(
                "trip day was already claimed or trip changed concurrently"
            ) from exc
        raise
    return response["Attributes"]


def rollback_next_day_slot(
    *,
    user_sub: str,
    trip_id: str,
    expected_next_day_index: int,
    status: str,
    table: DynamoDBTable | None = None,
) -> None:
    """Best-effort undo of ``claim_next_day_slot`` if DAY persist fails."""
    tbl = table or get_table()
    try:
        tbl.update_item(
            Key={"pk": keys.user_pk(user_sub), "sk": keys.trip_sk(trip_id)},
            UpdateExpression="SET #ndi = :expected, #st = :st, #ua = :ua",
            ExpressionAttributeNames={
                "#ndi": "next_day_index",
                "#st": "status",
                "#ua": "updated_at",
            },
            ExpressionAttributeValues={
                ":expected": expected_next_day_index,
                ":claimed": expected_next_day_index + 1,
                ":st": status,
                ":ua": _now_iso(),
            },
            ConditionExpression="next_day_index = :claimed",
        )
    except Exception:
        # Another writer may have moved on; leave state for the next request.
        return


def put_day_if_absent(
    *,
    user_sub: str,
    trip_id: str,
    day: DynamoItem,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    """Write a DAY row only if it does not already exist."""
    tbl = table or get_table()
    day_index = int(day["day_index"])
    item: DynamoItem = {
        "pk": keys.user_pk(user_sub),
        "sk": keys.day_sk(trip_id, day_index),
        "gsi1pk": keys.gsi1_pk(trip_id),
        "gsi1sk": keys.gsi1_sk_day(day_index),
        "entity_type": "DAY",
        "trip_id": trip_id,
        **day,
        "created_at": _now_iso(),
    }
    # Drop Nones — boto3 resource encodes them poorly in nested maps.
    cleaned = _strip_nones(item)
    if not isinstance(cleaned, dict):
        raise TypeError("day item must be a mapping")
    item = cleaned
    try:
        tbl.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    except Exception as exc:
        if _is_conditional_failure(exc):
            raise ConcurrentModificationError(
                "day already planned for this index"
            ) from exc
        raise
    return item


def persist_planned_day(
    *,
    user_sub: str,
    trip_id: str,
    day: DynamoItem,
    expected_next_day_index: int,
    visited_place_keys: list[str],
    prior_days_summary: str,
    new_status: str,
    rollback_status: str,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    """Claim day slot, write DAY if absent, then store visited/summary cursors.

    Claim-first avoids two concurrent planners both calling the LLM *and*
    both writing the same day: the second claim fails with conflict.
    """
    day_index = int(day["day_index"])
    if day_index != expected_next_day_index:
        raise ValueError("day_index must match expected_next_day_index")

    claim_next_day_slot(
        user_sub=user_sub,
        trip_id=trip_id,
        expected_next_day_index=expected_next_day_index,
        new_status=new_status,
        table=table,
    )
    try:
        day_item = put_day_if_absent(
            user_sub=user_sub,
            trip_id=trip_id,
            day=day,
            table=table,
        )
    except ConcurrentModificationError:
        rollback_next_day_slot(
            user_sub=user_sub,
            trip_id=trip_id,
            expected_next_day_index=expected_next_day_index,
            status=rollback_status,
            table=table,
        )
        raise

    update_trip(
        user_sub=user_sub,
        trip_id=trip_id,
        updates={
            "visited_place_keys": visited_place_keys,
            "prior_days_summary": prior_days_summary,
            "status": new_status,
        },
        table=table,
    )
    return day_item
