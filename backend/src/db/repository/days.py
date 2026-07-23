"""Day-plan row CRUD and suggest-place persistence."""

from __future__ import annotations

from typing import Any

from db import keys
from db.client import get_dynamodb_client, get_table
from db.dynamo_sanitize import (
    prepare_dynamo_item,
    prepare_dynamo_value,
    serialize_dynamo_attr,
)
from db.protocols import DynamoDBClient, DynamoDBTable
from db.repository.common import (
    ConcurrentModificationError,
    DynamoItem,
    PersistenceError,
    is_conditional_failure,
    now_iso,
    resolve_table,
)
from db.repository.trips import get_trip_meta


def put_day(
    *,
    user_sub: str,
    trip_id: str,
    day: DynamoItem,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    tbl = resolve_table(table)
    day_index = int(day["day_index"])
    item: DynamoItem = {
        "pk": keys.user_pk(user_sub),
        "sk": keys.day_sk(trip_id, day_index),
        "gsi1pk": keys.gsi1_pk(trip_id),
        "gsi1sk": keys.gsi1_sk_day(day_index),
        "entity_type": "DAY",
        "trip_id": trip_id,
        **day,
        "created_at": now_iso(),
    }
    cleaned = prepare_dynamo_item(item)
    tbl.put_item(Item=cleaned)
    return cleaned


def put_day_if_absent(
    *,
    user_sub: str,
    trip_id: str,
    day: DynamoItem,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    """Write a DAY row only if it does not already exist."""
    tbl = resolve_table(table)
    day_index = int(day["day_index"])
    item: DynamoItem = {
        "pk": keys.user_pk(user_sub),
        "sk": keys.day_sk(trip_id, day_index),
        "gsi1pk": keys.gsi1_pk(trip_id),
        "gsi1sk": keys.gsi1_sk_day(day_index),
        "entity_type": "DAY",
        "trip_id": trip_id,
        **day,
        "created_at": now_iso(),
    }
    # Drop Nones / floats — boto3 resource encodes them poorly in nested maps.
    cleaned = prepare_dynamo_item(item)
    try:
        tbl.put_item(Item=cleaned, ConditionExpression="attribute_not_exists(pk)")
    except Exception as exc:
        if is_conditional_failure(exc):
            raise ConcurrentModificationError(
                "day already planned for this index"
            ) from exc
        raise
    return cleaned


def get_day(
    *,
    user_sub: str,
    trip_id: str,
    day_index: int,
    table: DynamoDBTable | None = None,
) -> DynamoItem | None:
    """Point-read a single DAY item."""
    tbl = resolve_table(table)
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
    tbl = resolve_table(table)
    try:
        response = tbl.update_item(
            Key={"pk": keys.user_pk(user_sub), "sk": keys.day_sk(trip_id, day_index)},
            UpdateExpression="SET #places = :places, #ua = :ua",
            ExpressionAttributeNames={"#places": "places", "#ua": "updated_at"},
            ExpressionAttributeValues={
                ":places": prepare_dynamo_value(places),
                ":ua": now_iso(),
                ":expected": expected_place_count,
            },
            ConditionExpression=(
                "attribute_exists(pk) AND size(#places) = :expected"
            ),
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if is_conditional_failure(exc):
            raise ConcurrentModificationError(
                "day places changed concurrently; retry suggest-place"
            ) from exc
        raise
    return response["Attributes"]


def delete_day(
    *,
    user_sub: str,
    trip_id: str,
    day_index: int,
    table: DynamoDBTable | None = None,
) -> bool:
    """Delete a DAY row. Returns True if an item was removed."""
    tbl = resolve_table(table)
    existing = get_day(
        user_sub=user_sub, trip_id=trip_id, day_index=day_index, table=tbl
    )
    if not existing:
        return False
    tbl.delete_item(
        Key={"pk": keys.user_pk(user_sub), "sk": keys.day_sk(trip_id, day_index)}
    )
    return True


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

    Looks up helpers via ``db.repository`` so tests can monkeypatch
    ``repo.put_day_if_absent`` / claim helpers on the package.
    """
    # Late import: package ``__init__`` is fully loaded by the time this runs.
    from db import repository as repo

    day_index = int(day["day_index"])
    if day_index != expected_next_day_index:
        raise ValueError("day_index must match expected_next_day_index")

    repo.claim_next_day_slot(
        user_sub=user_sub,
        trip_id=trip_id,
        expected_next_day_index=expected_next_day_index,
        new_status=new_status,
        table=table,
    )
    # Re-check after long crew calls: delete may have marked the trip deleting
    # (or removed it) between claim and Put.
    live = repo.get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=table)
    if not live or str(live.get("status") or "") == "deleting":
        # Do not rollback — that would overwrite the delete lock / missing trip.
        raise repo.ConcurrentModificationError("trip is being deleted")
    try:
        day_item = repo.put_day_if_absent(
            user_sub=user_sub,
            trip_id=trip_id,
            day=day,
            table=table,
        )
    except Exception:
        # Any Put failure (float types, network, conflict) must rewind the cursor
        # or the next plan-next-day skips this index (e.g. day 1 missing, day 2 shown).
        # Do not overwrite a delete lock.
        live_after = repo.get_trip_meta(
            user_sub=user_sub, trip_id=trip_id, table=table
        )
        if live_after and str(live_after.get("status") or "") != "deleting":
            repo.rollback_next_day_slot(
                user_sub=user_sub,
                trip_id=trip_id,
                expected_next_day_index=expected_next_day_index,
                status=rollback_status,
                table=table,
            )
        raise

    live_after_put = repo.get_trip_meta(
        user_sub=user_sub, trip_id=trip_id, table=table
    )
    if not live_after_put or str(live_after_put.get("status") or "") == "deleting":
        # Bundle delete may have already run; remove the day we just wrote.
        repo.delete_day(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            table=table,
        )
        raise repo.ConcurrentModificationError("trip is being deleted")

    repo.update_trip(
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
    cleaned_places = prepare_dynamo_value(places)
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

    now = now_iso()
    updated_visited = [*previous_visited, key]
    client = _dynamo_client(table)
    name = _table_name_for(table)
    pk = keys.user_pk(user_sub)

    day_update: dict[str, Any] = {
        "Update": {
            "TableName": name,
            "Key": {
                "pk": serialize_dynamo_attr(pk),
                "sk": serialize_dynamo_attr(keys.day_sk(trip_id, day_index)),
            },
            "UpdateExpression": "SET #places = :places, #ua = :ua",
            "ExpressionAttributeNames": {"#places": "places", "#ua": "updated_at"},
            "ExpressionAttributeValues": {
                ":places": serialize_dynamo_attr(cleaned_places),
                ":ua": serialize_dynamo_attr(now),
                ":expected": serialize_dynamo_attr(expected_place_count),
            },
            "ConditionExpression": "attribute_exists(pk) AND size(#places) = :expected",
        }
    }

    trip_values: dict[str, Any] = {
        ":new": serialize_dynamo_attr(updated_visited),
        ":ua": serialize_dynamo_attr(now),
        ":prev": serialize_dynamo_attr(previous_visited),
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
                "pk": serialize_dynamo_attr(pk),
                "sk": serialize_dynamo_attr(keys.trip_sk(trip_id)),
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
        if _is_transaction_canceled(exc) or is_conditional_failure(exc):
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
