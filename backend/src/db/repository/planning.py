"""Optimistic locks and cursors for plan-next-day / itinerary edits."""

from __future__ import annotations

from datetime import datetime, timezone

from db import keys
from db.protocols import DynamoDBTable
from db.repository.common import (
    ConcurrentModificationError,
    DynamoItem,
    is_conditional_failure,
    now_iso,
    resolve_table,
)
from db.repository.trips import get_trip_meta

# Async plan-next-day: lock via planning_day_index without advancing next_day_index.
PLANNING_STALE_SECONDS = 6 * 60


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
    Refuses trips marked ``status=deleting``.
    """
    tbl = resolve_table(table)
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
                ":ua": now_iso(),
                ":deleting": "deleting",
            },
            ConditionExpression=(
                "next_day_index = :expected AND #st <> :deleting"
            ),
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if is_conditional_failure(exc):
            raise ConcurrentModificationError(
                "trip day was already claimed or trip changed concurrently"
            ) from exc
        raise
    return response["Attributes"]


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
    tbl = resolve_table(table)
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
                ":ua": now_iso(),
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
    tbl = resolve_table(table)
    now = now_iso()
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
                ":deleting": "deleting",
            },
            ConditionExpression=(
                "#ndi = :expected AND attribute_not_exists(#pdi) AND #st <> :deleting"
            ),
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if is_conditional_failure(exc):
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
    tbl = resolve_table(table)
    now = now_iso()
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
        if is_conditional_failure(exc):
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
    tbl = resolve_table(table)
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
                ":ua": now_iso(),
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
    tbl = resolve_table(table)
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
                ":ua": now_iso(),
            },
            ConditionExpression="next_day_index = :claimed",
        )
    except Exception:
        # Another writer may have moved on; leave state for the next request.
        return


def apply_itinerary_edit(
    *,
    user_sub: str,
    trip_id: str,
    next_day_index: int,
    status: str,
    prior_days_summary: str,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    """After deleting a day: sync cursors. Fails if a planning claim is held.

    Does not rewrite ``visited_place_keys`` — callers should prune unused keys
    separately so concurrent suggest-place appends are not wiped.
    """
    tbl = resolve_table(table)
    try:
        response = tbl.update_item(
            Key={"pk": keys.user_pk(user_sub), "sk": keys.trip_sk(trip_id)},
            UpdateExpression=(
                "SET #ndi = :ndi, #pds = :pds, #st = :st, #ua = :ua "
                "REMOVE #pe"
            ),
            ExpressionAttributeNames={
                "#ndi": "next_day_index",
                "#pds": "prior_days_summary",
                "#st": "status",
                "#ua": "updated_at",
                "#pdi": "planning_day_index",
                "#pe": "planning_error",
            },
            ExpressionAttributeValues={
                ":ndi": next_day_index,
                ":pds": prior_days_summary,
                ":st": status,
                ":ua": now_iso(),
                ":deleting": "deleting",
            },
            ConditionExpression=(
                "attribute_exists(pk) AND attribute_not_exists(#pdi) "
                "AND #st <> :deleting"
            ),
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if is_conditional_failure(exc):
            raise ConcurrentModificationError(
                "cannot edit itinerary while a day is being planned or deleted"
            ) from exc
        raise
    return response["Attributes"]
