"""Remap DAY rows when a city route is reconfirmed.

Owns itinerary remap orchestration (ADR 005). Uses Dynamo helpers from
``db.repository`` but must never import ``trips.service.TripService``.
"""

from __future__ import annotations

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
    from trips.day_status import status_after_day_edit
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

