"""Trip meta + route persistence and trip-scoped queries."""

from __future__ import annotations

from typing import Any

from db import keys
from db.dynamo_sanitize import prepare_dynamo_item
from db.protocols import DynamoDBTable
from db.repository.common import (
    ConcurrentModificationError,
    DynamoItem,
    is_conditional_failure,
    now_iso,
    resolve_table,
)
from db.schema import GSI1_NAME


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
    tbl = resolve_table(table)
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
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    cleaned = prepare_dynamo_item(item)
    tbl.put_item(Item=cleaned)
    return cleaned


def put_route(
    *,
    user_sub: str,
    trip_id: str,
    route: DynamoItem,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    tbl = resolve_table(table)
    item: DynamoItem = {
        "pk": keys.user_pk(user_sub),
        "sk": keys.route_sk(trip_id),
        "gsi1pk": keys.gsi1_pk(trip_id),
        "gsi1sk": keys.gsi1_sk_route(),
        "entity_type": "ROUTE",
        "trip_id": trip_id,
        **route,
        "updated_at": now_iso(),
    }
    cleaned = prepare_dynamo_item(item)
    tbl.put_item(Item=cleaned)
    return cleaned


def delete_route(
    *,
    user_sub: str,
    trip_id: str,
    table: DynamoDBTable | None = None,
) -> None:
    """Remove the ROUTE item if present (date edits invalidate proposals)."""
    tbl = resolve_table(table)
    tbl.delete_item(Key={"pk": keys.user_pk(user_sub), "sk": keys.route_sk(trip_id)})


def list_trip_meta_for_user(
    *,
    user_sub: str,
    table: DynamoDBTable | None = None,
) -> list[DynamoItem]:
    """List TRIP meta rows only (exclude ROUTE/DAY)."""
    tbl = resolve_table(table)
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
    """Trip meta + route + days for one trip (same partition prefix).

    Paginated: every ``TRIP#{id}``, ``TRIP#{id}#ROUTE``, and ``TRIP#{id}#DAY#…``
    row under the user partition is returned.
    """
    tbl = resolve_table(table)
    prefix = keys.trip_sk(trip_id)
    items: list[DynamoItem] = []
    start_key: dict[str, Any] | None = None
    while True:
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
            "ExpressionAttributeValues": {
                ":pk": keys.user_pk(user_sub),
                ":prefix": prefix,
            },
        }
        if start_key:
            kwargs["ExclusiveStartKey"] = start_key
        response = tbl.query(**kwargs)
        items.extend(list(response.get("Items") or []))
        start_key = response.get("LastEvaluatedKey")
        if not start_key:
            break
    return items


def delete_trip_bundle(
    *,
    user_sub: str,
    trip_id: str,
    table: DynamoDBTable | None = None,
) -> dict[str, int]:
    """Delete every row for a trip: TRIP meta, ROUTE, and all DAY plans.

    Returns counts by ``entity_type`` (plus ``total``).
    """
    tbl = resolve_table(table)
    items = get_trip_bundle(user_sub=user_sub, trip_id=trip_id, table=tbl)
    counts: dict[str, int] = {"TRIP": 0, "ROUTE": 0, "DAY": 0, "total": 0}
    for item in items:
        pk = item.get("pk")
        sk = item.get("sk")
        if not pk or not sk:
            continue
        et = str(item.get("entity_type") or "UNKNOWN")
        tbl.delete_item(Key={"pk": pk, "sk": sk})
        counts["total"] += 1
        if et in counts:
            counts[et] += 1
    return counts


def get_trip_by_id_via_gsi(
    *,
    trip_id: str,
    table: DynamoDBTable | None = None,
) -> list[DynamoItem]:
    """Lookup by trip_id using GSI1 (still authorize with user_sub in the API layer)."""
    tbl = resolve_table(table)
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
    tbl = resolve_table(table)
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
    tbl = resolve_table(table)
    payload: DynamoItem = prepare_dynamo_item({**updates, "updated_at": now_iso()})
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


def begin_trip_delete(
    *,
    user_sub: str,
    trip_id: str,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    """Mark trip ``status=deleting`` only when no planning claim is held.

    Acts as a delete lock so an async plan worker can refuse to write after this
    point, and concurrent plan claims lose the race.
    """
    tbl = resolve_table(table)
    try:
        response = tbl.update_item(
            Key={"pk": keys.user_pk(user_sub), "sk": keys.trip_sk(trip_id)},
            UpdateExpression="SET #st = :del, #ua = :ua",
            ExpressionAttributeNames={
                "#st": "status",
                "#ua": "updated_at",
                "#pdi": "planning_day_index",
            },
            ExpressionAttributeValues={
                ":del": "deleting",
                ":ua": now_iso(),
            },
            ConditionExpression=(
                "attribute_exists(pk) AND attribute_not_exists(#pdi)"
            ),
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if is_conditional_failure(exc):
            raise ConcurrentModificationError(
                "cannot delete trip while planning is in progress"
            ) from exc
        raise
    return response["Attributes"]


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
    tbl = resolve_table(table)
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
            ":ua": now_iso(),
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
            if is_conditional_failure(exc):
                continue
            raise
    raise ConcurrentModificationError(
        "could not append visited place key; retry suggest-place"
    )


def prune_visited_place_keys(
    *,
    user_sub: str,
    trip_id: str,
    keys_to_remove: set[str] | list[str],
    table: DynamoDBTable | None = None,
    max_attempts: int = 5,
) -> DynamoItem:
    """Drop keys from TRIP.visited_place_keys with optimistic concurrency.

    Preserves keys added concurrently (e.g. suggest-place on another day) by
    only removing the requested set from the latest list.
    """
    tbl = resolve_table(table)
    remove = {str(k).strip() for k in keys_to_remove if str(k).strip()}
    if not remove:
        trip = get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=tbl)
        if not trip:
            raise ConcurrentModificationError("trip not found while pruning visited keys")
        return trip

    for _ in range(max_attempts):
        trip = get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=tbl)
        if not trip:
            raise ConcurrentModificationError("trip not found while pruning visited keys")
        previous = list(trip.get("visited_place_keys") or [])
        updated = [k for k in previous if str(k) not in remove]
        if updated == previous:
            return trip
        names = {"#v": "visited_place_keys", "#ua": "updated_at"}
        values: DynamoItem = {
            ":new": updated,
            ":ua": now_iso(),
            ":prev": previous,
        }
        if previous:
            condition = "attribute_exists(pk) AND #v = :prev"
        else:
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
            if is_conditional_failure(exc):
                continue
            raise
    raise ConcurrentModificationError(
        "could not prune visited place keys; retry"
    )
