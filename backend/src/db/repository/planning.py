"""Optimistic locks and cursors for plan-next-day / itinerary edits."""

from __future__ import annotations

from datetime import datetime, timezone

from db import keys
from db.protocols import DynamoDBTable
from db.repository.common import (
    ConcurrentModificationError,
    DynamoItem,
    PersistenceError,
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
                "#cjk": "crew_job_kind",
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
                "#ndi = :expected AND attribute_not_exists(#pdi) "
                "AND attribute_not_exists(#cjk) AND #st <> :deleting"
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


def remap_itinerary_for_route_reconfirm(
    *,
    user_sub: str,
    trip_id: str,
    route: DynamoItem,
    start_date: str,
    day_count: int,
    destination: str,
    previous_status: str,
    table: DynamoDBTable | None = None,
) -> tuple[list[DynamoItem], DynamoItem]:
    """Remap DAY rows onto a new city route; rebuild planning cursors.

    Write-before-delete with staging keys (``DAYREMAP#``):

    1. Stage every kept plan (with route fingerprint) and verify read-back.
    2. Delete old ``DAY#`` rows only after staging succeeds.
    3. Promote staging → final ``DAY#`` keys.
    4. Drop staging only after every final put succeeds.

    Resume rules:
    - Any ``DAY_REMAP`` rows are authoritative: promote them first.
    - If their route fingerprint matches this confirm, keep those days.
    - If fingerprint mismatches, remap the recovered days onto the new route.
    - No staging → remap from existing ``DAY`` rows (write-before-delete).

    Force-clears an in-flight planning claim. Returns
    ``(kept_day_items, updated_trip)``.
    """
    from datetime import date as date_cls

    from db.dynamo_sanitize import prepare_dynamo_item
    from db.repository.days import put_day
    from db.repository.trips import get_trip_bundle, get_trip_meta
    from trips.day_edit import status_after_day_edit
    from trips.day_remap import remap_day_plans, route_remap_fingerprint
    from trips.prompts import rebuild_prior_days_summary, visited_keys_from_days

    tbl = resolve_table(table)
    pk = keys.user_pk(user_sub)
    route_fp = route_remap_fingerprint(route)

    def _delete_key(sk: str) -> None:
        tbl.delete_item(Key={"pk": pk, "sk": sk})

    def _day_payload(item: DynamoItem) -> DynamoItem:
        skip = {
            "pk",
            "sk",
            "gsi1pk",
            "gsi1sk",
            "entity_type",
            "trip_id",
            "updated_at",
            "created_at",
            "remap_route_fp",
        }
        return {k: v for k, v in item.items() if k not in skip}

    def _put_staging(day_index: int, payload: DynamoItem) -> None:
        item: DynamoItem = {
            "pk": pk,
            "sk": keys.day_remap_staging_sk(trip_id, day_index),
            "gsi1pk": keys.gsi1_pk(trip_id),
            "gsi1sk": f"DAYREMAP#{day_index:02d}",
            "entity_type": "DAY_REMAP",
            "trip_id": trip_id,
            "remap_route_fp": route_fp,
            **payload,
            "updated_at": now_iso(),
        }
        tbl.put_item(Item=prepare_dynamo_item(item))

    def _delete_staging_rows(rows: list[DynamoItem]) -> None:
        for item in rows:
            sk = item.get("sk")
            if sk:
                _delete_key(str(sk))

    def _promote_payloads(payloads: list[DynamoItem]) -> list[DynamoItem]:
        kept: list[DynamoItem] = []
        for clean in payloads:
            written = put_day(
                user_sub=user_sub,
                trip_id=trip_id,
                day=clean,
                table=tbl,
            )
            kept.append(written)
        return kept

    def _stage_all(payloads: list[DynamoItem]) -> list[DynamoItem]:
        staged: list[DynamoItem] = []
        try:
            for payload in payloads:
                clean = {k: v for k, v in payload.items() if k != "created_at"}
                day_index = int(clean["day_index"])
                _put_staging(day_index, clean)
                read_back = tbl.get_item(
                    Key={
                        "pk": pk,
                        "sk": keys.day_remap_staging_sk(trip_id, day_index),
                    }
                ).get("Item")
                if not read_back or read_back.get("entity_type") != "DAY_REMAP":
                    raise PersistenceError(
                        f"failed to stage remapped day_index={day_index} "
                        "before deleting old days"
                    )
                staged.append(clean)
        except Exception:
            # Partial staging must not trigger resume that deletes surviving DAY rows.
            bundle_now = get_trip_bundle(
                user_sub=user_sub, trip_id=trip_id, table=tbl
            )
            _delete_staging_rows(
                [i for i in bundle_now if i.get("entity_type") == "DAY_REMAP"]
            )
            raise
        return staged

    try:
        tbl.update_item(
            Key={"pk": pk, "sk": keys.trip_sk(trip_id)},
            UpdateExpression="REMOVE #pdi, #psa, #pe SET #ua = :ua",
            ExpressionAttributeNames={
                "#pdi": "planning_day_index",
                "#psa": "planning_started_at",
                "#pe": "planning_error",
                "#ua": "updated_at",
                "#st": "status",
            },
            ExpressionAttributeValues={
                ":ua": now_iso(),
                ":deleting": "deleting",
            },
            ConditionExpression="attribute_exists(pk) AND #st <> :deleting",
        )
    except Exception as exc:
        if is_conditional_failure(exc):
            raise ConcurrentModificationError(
                "cannot remap itinerary while trip is being deleted"
            ) from exc
        raise

    bundle = get_trip_bundle(user_sub=user_sub, trip_id=trip_id, table=tbl)
    existing_staging = [i for i in bundle if i.get("entity_type") == "DAY_REMAP"]
    old_days = [i for i in bundle if i.get("entity_type") == "DAY"]
    start = date_cls.fromisoformat(str(start_date)[:10])

    if existing_staging:
        # Staging is authoritative (covers promote-interrupted and stage-complete).
        staging_fps = {str(i.get("remap_route_fp") or "") for i in existing_staging}
        staged_payloads = [
            _day_payload(i)
            for i in sorted(
                existing_staging, key=lambda d: int(d.get("day_index") or 0)
            )
        ]
        recovered = _promote_payloads(staged_payloads)
        _delete_staging_rows(existing_staging)
        # Drop any leftover DAY rows not covered by staging (should be rare).
        staged_indexes = {int(p["day_index"]) for p in staged_payloads}
        for item in old_days:
            if int(item.get("day_index") or 0) in staged_indexes:
                continue
            sk = item.get("sk")
            if sk:
                _delete_key(str(sk))

        if staging_fps == {route_fp}:
            kept = recovered
        else:
            remapped = remap_day_plans(
                recovered,
                route=route,
                day_count=int(day_count),
                start_date=start,
                destination=destination,
            )
            staged_payloads = _stage_all(remapped)
            for item in recovered:
                sk = item.get("sk")
                if sk:
                    _delete_key(str(sk))
            kept = _promote_payloads(staged_payloads)
            bundle_after = get_trip_bundle(
                user_sub=user_sub, trip_id=trip_id, table=tbl
            )
            _delete_staging_rows(
                [i for i in bundle_after if i.get("entity_type") == "DAY_REMAP"]
            )
    else:
        remapped = remap_day_plans(
            old_days,
            route=route,
            day_count=int(day_count),
            start_date=start,
            destination=destination,
        )
        staged_payloads = _stage_all(remapped)
        for item in old_days:
            sk = item.get("sk")
            if sk:
                _delete_key(str(sk))
        kept = _promote_payloads(staged_payloads)
        bundle_after = get_trip_bundle(
            user_sub=user_sub, trip_id=trip_id, table=tbl
        )
        _delete_staging_rows(
            [i for i in bundle_after if i.get("entity_type") == "DAY_REMAP"]
        )

    next_day_index, new_status = status_after_day_edit(
        remaining_days=kept,
        day_count=int(day_count),
        previous_status=previous_status,
    )
    if not kept:
        next_day_index, new_status = 1, "routing_confirmed"
    elif new_status == "complete":
        pass
    else:
        new_status = "planning"

    visited = visited_keys_from_days(kept)
    prior = rebuild_prior_days_summary(kept)
    try:
        response = tbl.update_item(
            Key={"pk": pk, "sk": keys.trip_sk(trip_id)},
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
                ":vpk": visited,
                ":pds": prior,
                ":st": new_status,
                ":ua": now_iso(),
                ":deleting": "deleting",
            },
            ConditionExpression="attribute_exists(pk) AND #st <> :deleting",
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if is_conditional_failure(exc):
            raise ConcurrentModificationError(
                "cannot remap itinerary while trip is being deleted"
            ) from exc
        raise

    trip_out = response["Attributes"]
    if not trip_out:
        trip_out = get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=tbl) or {}
    return kept, trip_out



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
