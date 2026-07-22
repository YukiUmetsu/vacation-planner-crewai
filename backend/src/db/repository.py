"""Minimal single-table persistence for trips / routes / days."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from db import keys
from db.client import get_dynamodb_client, get_table
from db.protocols import DynamoDBClient, DynamoDBTable
from db.schema import GSI1_NAME

# DynamoDB item documents (keys + attributes). Numbers may be Decimal from boto3.
DynamoItem = dict[str, Any]


class ConcurrentModificationError(Exception):
    """Raised when a conditional DynamoDB write loses a race."""


class PersistenceError(Exception):
    """Unexpected DynamoDB/client failure (not an optimistic-lock conflict)."""


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
    Used by the sync ``persist_planned_day`` path (fake/local).
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


# Async plan-next-day: lock via planning_day_index without advancing next_day_index.
PLANNING_STALE_SECONDS = 6 * 60


def clear_stale_planning_claim(
    *,
    user_sub: str,
    trip_id: str,
    stale_after_seconds: int = PLANNING_STALE_SECONDS,
    table: DynamoDBTable | None = None,
) -> bool:
    """Clear a stuck ``planning_day_index`` if ``planning_started_at`` is too old.

    Returns True when a stale claim was cleared.
    """
    trip = get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=table)
    if not trip or trip.get("planning_day_index") is None:
        return False
    started = str(trip.get("planning_started_at") or "").strip()
    if not started:
        return False
    try:
        started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
    except ValueError:
        started_dt = None
    if started_dt is None:
        return False
    if started_dt.tzinfo is None:
        started_dt = started_dt.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - started_dt.astimezone(timezone.utc)).total_seconds()
    if age < stale_after_seconds:
        return False
    tbl = table or get_table()
    try:
        tbl.update_item(
            Key={"pk": keys.user_pk(user_sub), "sk": keys.trip_sk(trip_id)},
            UpdateExpression=(
                "REMOVE #pdi, #psa, #pe SET #ua = :ua, #st = :st"
            ),
            ExpressionAttributeNames={
                "#pdi": "planning_day_index",
                "#psa": "planning_started_at",
                "#pe": "planning_error",
                "#ua": "updated_at",
                "#st": "status",
            },
            ExpressionAttributeValues={
                ":ua": _now_iso(),
                ":st": "planning",
                ":expected_pdi": trip["planning_day_index"],
            },
            ConditionExpression="planning_day_index = :expected_pdi",
        )
    except Exception:
        return False
    return True


def claim_planning_in_progress(
    *,
    user_sub: str,
    trip_id: str,
    expected_next_day_index: int,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    """Mark day N as in-flight without advancing ``next_day_index``.

    Concurrent planners lose with ``ConcurrentModificationError``.
    """
    clear_stale_planning_claim(
        user_sub=user_sub, trip_id=trip_id, table=table
    )
    tbl = table or get_table()
    now = _now_iso()
    try:
        response = tbl.update_item(
            Key={"pk": keys.user_pk(user_sub), "sk": keys.trip_sk(trip_id)},
            UpdateExpression=(
                "SET #pdi = :pdi, #psa = :psa, #st = :st, #ua = :ua "
                "REMOVE #pe"
            ),
            ExpressionAttributeNames={
                "#pdi": "planning_day_index",
                "#psa": "planning_started_at",
                "#pe": "planning_error",
                "#st": "status",
                "#ua": "updated_at",
                "#ndi": "next_day_index",
            },
            ExpressionAttributeValues={
                ":pdi": expected_next_day_index,
                ":psa": now,
                ":st": "planning",
                ":ua": now,
                ":expected": expected_next_day_index,
            },
            ConditionExpression=(
                "#ndi = :expected AND attribute_not_exists(#pdi)"
            ),
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if _is_conditional_failure(exc):
            raise ConcurrentModificationError(
                "a day is already being planned for this trip"
            ) from exc
        raise
    return response["Attributes"]


def complete_planning_after_day_write(
    *,
    user_sub: str,
    trip_id: str,
    planned_day_index: int,
    next_day_index: int,
    visited_place_keys: list[str],
    prior_days_summary: str,
    new_status: str,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    """After DAY Put: advance cursor, clear in-flight planning fields."""
    tbl = table or get_table()
    now = _now_iso()
    try:
        response = tbl.update_item(
            Key={"pk": keys.user_pk(user_sub), "sk": keys.trip_sk(trip_id)},
            UpdateExpression=(
                "SET #ndi = :ndi, #vpk = :vpk, #pds = :pds, #st = :st, #ua = :ua "
                "REMOVE #pdi, #psa, #pe"
            ),
            ExpressionAttributeNames={
                "#ndi": "next_day_index",
                "#vpk": "visited_place_keys",
                "#pds": "prior_days_summary",
                "#st": "status",
                "#ua": "updated_at",
                "#pdi": "planning_day_index",
                "#psa": "planning_started_at",
                "#pe": "planning_error",
            },
            ExpressionAttributeValues={
                ":ndi": next_day_index,
                ":vpk": visited_place_keys,
                ":pds": prior_days_summary,
                ":st": new_status,
                ":ua": now,
                ":expected_pdi": planned_day_index,
            },
            ConditionExpression="planning_day_index = :expected_pdi",
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if _is_conditional_failure(exc):
            raise ConcurrentModificationError(
                "planning claim lost before completion"
            ) from exc
        raise
    return response["Attributes"]


def fail_planning_in_progress(
    *,
    user_sub: str,
    trip_id: str,
    planned_day_index: int,
    error_message: str,
    table: DynamoDBTable | None = None,
) -> None:
    """Clear in-flight claim and record ``planning_error`` / ``status=failed``."""
    tbl = table or get_table()
    msg = (error_message or "planning failed")[:500]
    try:
        tbl.update_item(
            Key={"pk": keys.user_pk(user_sub), "sk": keys.trip_sk(trip_id)},
            UpdateExpression=(
                "SET #st = :st, #pe = :pe, #ua = :ua REMOVE #pdi, #psa"
            ),
            ExpressionAttributeNames={
                "#st": "status",
                "#pe": "planning_error",
                "#ua": "updated_at",
                "#pdi": "planning_day_index",
                "#psa": "planning_started_at",
            },
            ExpressionAttributeValues={
                ":st": "failed",
                ":pe": msg,
                ":ua": _now_iso(),
                ":expected_pdi": planned_day_index,
            },
            ConditionExpression="planning_day_index = :expected_pdi",
        )
    except Exception:
        return


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


def get_day(
    *,
    user_sub: str,
    trip_id: str,
    day_index: int,
    table: DynamoDBTable | None = None,
) -> DynamoItem | None:
    """Point-read a single DAY item."""
    tbl = table or get_table()
    response = tbl.get_item(
        Key={"pk": keys.user_pk(user_sub), "sk": keys.day_sk(trip_id, day_index)},
    )
    item = response.get("Item")
    if not item or item.get("entity_type") != "DAY":
        return None
    return item


def replace_day_places(
    *,
    user_sub: str,
    trip_id: str,
    day_index: int,
    places: list[DynamoItem],
    expected_place_count: int,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    """Replace DAY.places with optimistic lock on previous place count."""
    tbl = table or get_table()
    try:
        response = tbl.update_item(
            Key={"pk": keys.user_pk(user_sub), "sk": keys.day_sk(trip_id, day_index)},
            UpdateExpression="SET #places = :places, #ua = :ua",
            ExpressionAttributeNames={"#places": "places", "#ua": "updated_at"},
            ExpressionAttributeValues={
                ":places": _strip_nones(places),
                ":ua": _now_iso(),
                ":expected": expected_place_count,
            },
            ConditionExpression=(
                "attribute_exists(pk) AND size(#places) = :expected"
            ),
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if _is_conditional_failure(exc):
            raise ConcurrentModificationError(
                "day places changed concurrently; retry suggest-place"
            ) from exc
        raise
    return response["Attributes"]


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


def _dynamo_client(_table: DynamoDBTable | None = None) -> DynamoDBClient:
    """Low-level DynamoDB client for TransactWriteItems.

    Do not use ``table.meta.client`` with TypeSerializer payloads — the resource
    client path can re-encode AttributeValue dicts and moto/AWS then fail with
    ``unhashable type: 'dict'``.
    """
    return get_dynamodb_client()


def _table_name_for(table: DynamoDBTable | None) -> str:
    if table is not None and getattr(table, "name", None):
        return str(table.name)
    return get_table().name


def _dynamo_safe(value: Any) -> Any:
    """Normalize Decimals / nested structures for low-level TypeSerializer."""
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, list):
        return [_dynamo_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _dynamo_safe(v) for k, v in value.items()}
    return value


def _is_transaction_canceled(exc: BaseException) -> bool:
    response = getattr(exc, "response", None) or {}
    if not isinstance(response, dict):
        response = {}
    code = (response.get("Error") or {}).get("Code", "")
    name = type(exc).__name__
    return code == "TransactionCanceledException" or "TransactionCanceled" in name


def persist_suggested_place(
    *,
    user_sub: str,
    trip_id: str,
    day_index: int,
    places: list[DynamoItem],
    expected_place_count: int,
    place_key: str,
    previous_visited_keys: list[str],
    table: DynamoDBTable | None = None,
) -> tuple[DynamoItem, DynamoItem]:
    """Atomically update DAY.places and TRIP.visited_place_keys via TransactWriteItems.

    If the new place_key is already on the trip visited list, only the day row is
    updated (single conditional write).
    """
    cleaned_places = _strip_nones(places)
    if not isinstance(cleaned_places, list):
        raise TypeError("places must be a list")
    if len(cleaned_places) != expected_place_count + 1:
        raise ValueError(
            "places must be previous day places plus exactly one suggested place"
        )

    key = str(place_key or "").strip()
    previous_visited = list(previous_visited_keys)

    # Already tracked — day-only write (no visited mutation to coordinate).
    if not key or key in previous_visited:
        day_item = replace_day_places(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            places=cleaned_places,  # type: ignore[arg-type]
            expected_place_count=expected_place_count,
            table=table,
        )
        trip = get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=table)
        if not trip:
            raise ConcurrentModificationError("trip not found after day update")
        return day_item, trip

    from boto3.dynamodb.types import TypeSerializer

    serializer = TypeSerializer()
    now = _now_iso()
    safe_places = _dynamo_safe(cleaned_places)
    updated_visited = [*previous_visited, key]
    client = _dynamo_client(table)
    name = _table_name_for(table)
    pk = keys.user_pk(user_sub)

    day_update: dict[str, Any] = {
        "Update": {
            "TableName": name,
            "Key": {
                "pk": serializer.serialize(pk),
                "sk": serializer.serialize(keys.day_sk(trip_id, day_index)),
            },
            "UpdateExpression": "SET #places = :places, #ua = :ua",
            "ExpressionAttributeNames": {"#places": "places", "#ua": "updated_at"},
            "ExpressionAttributeValues": {
                ":places": serializer.serialize(safe_places),
                ":ua": serializer.serialize(now),
                ":expected": serializer.serialize(expected_place_count),
            },
            "ConditionExpression": "attribute_exists(pk) AND size(#places) = :expected",
        }
    }

    trip_values: dict[str, Any] = {
        ":new": serializer.serialize(updated_visited),
        ":ua": serializer.serialize(now),
        ":prev": serializer.serialize(previous_visited),
    }
    if previous_visited:
        trip_condition = "attribute_exists(pk) AND #v = :prev"
    else:
        trip_condition = (
            "attribute_exists(pk) AND (attribute_not_exists(#v) OR #v = :prev)"
        )

    trip_update: dict[str, Any] = {
        "Update": {
            "TableName": name,
            "Key": {
                "pk": serializer.serialize(pk),
                "sk": serializer.serialize(keys.trip_sk(trip_id)),
            },
            "UpdateExpression": "SET #v = :new, #ua = :ua",
            "ExpressionAttributeNames": {
                "#v": "visited_place_keys",
                "#ua": "updated_at",
            },
            "ExpressionAttributeValues": trip_values,
            "ConditionExpression": trip_condition,
        }
    }

    try:
        client.transact_write_items(TransactItems=[day_update, trip_update])
    except Exception as exc:
        if _is_transaction_canceled(exc) or _is_conditional_failure(exc):
            raise ConcurrentModificationError(
                "suggest-place conflict on day places or visited keys; retry"
            ) from exc
        raise PersistenceError(
            f"suggest-place transaction failed: {type(exc).__name__}"
        ) from exc

    day_item = get_day(
        user_sub=user_sub, trip_id=trip_id, day_index=day_index, table=table
    )
    trip = get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=table)
    if not day_item or not trip:
        raise PersistenceError(
            "suggest-place transaction succeeded but items missing on re-read"
        )
    return day_item, trip


def append_visited_place_key(
    *,
    user_sub: str,
    trip_id: str,
    place_key: str,
    table: DynamoDBTable | None = None,
    max_attempts: int = 5,
) -> DynamoItem:
    """Append one key to TRIP.visited_place_keys with optimistic concurrency.

    Avoids lost updates when suggest-place races with plan-next-day (or another
    suggest) that also rewrites the visited list.
    """
    tbl = table or get_table()
    key = str(place_key or "").strip()
    if not key:
        trip = get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=tbl)
        if not trip:
            raise ConcurrentModificationError("trip not found while updating visited keys")
        return trip

    for _ in range(max_attempts):
        trip = get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=tbl)
        if not trip:
            raise ConcurrentModificationError("trip not found while updating visited keys")
        previous = list(trip.get("visited_place_keys") or [])
        if key in previous:
            return trip
        updated = [*previous, key]
        names = {"#v": "visited_place_keys", "#ua": "updated_at"}
        values: DynamoItem = {
            ":new": updated,
            ":ua": _now_iso(),
            ":prev": previous,
        }
        if previous:
            condition = "attribute_exists(pk) AND #v = :prev"
        else:
            # Brand-new trips always have [], but tolerate a missing attribute.
            condition = (
                "attribute_exists(pk) AND (attribute_not_exists(#v) OR #v = :prev)"
            )
        try:
            response = tbl.update_item(
                Key={"pk": keys.user_pk(user_sub), "sk": keys.trip_sk(trip_id)},
                UpdateExpression="SET #v = :new, #ua = :ua",
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
                ConditionExpression=condition,
                ReturnValues="ALL_NEW",
            )
            return response["Attributes"]
        except Exception as exc:
            if _is_conditional_failure(exc):
                continue
            raise
    raise ConcurrentModificationError(
        "could not append visited place key; retry suggest-place"
    )


def get_profile(*, user_sub: str, table: DynamoDBTable | None = None) -> DynamoItem | None:
    tbl = table or get_table()
    resp = tbl.get_item(Key={"pk": keys.user_pk(user_sub), "sk": keys.profile_sk()})
    item = resp.get("Item")
    return item if isinstance(item, dict) else None


def put_profile(
    *,
    user_sub: str,
    display_name: str = "",
    preferences: str = "",
    energy_level: int = 3,
    interests: list[str] | None = None,
    visited_places: list[dict[str, Any]] | None = None,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    tbl = table or get_table()
    now = _now_iso()
    existing = get_profile(user_sub=user_sub, table=tbl)
    created_at = str(existing.get("created_at") or now) if existing else now
    item: DynamoItem = {
        "pk": keys.user_pk(user_sub),
        "sk": keys.profile_sk(),
        "entity_type": "PROFILE",
        "user_id": user_sub,
        "display_name": display_name,
        "preferences": preferences,
        "energy_level": int(energy_level),
        "interests": list(interests or []),
        "visited_places": list(visited_places or []),
        "created_at": created_at,
        "updated_at": now,
    }
    cleaned = _strip_nones(item)
    if not isinstance(cleaned, dict):
        raise TypeError("profile item must be a mapping")
    tbl.put_item(Item=cleaned)
    return cleaned
