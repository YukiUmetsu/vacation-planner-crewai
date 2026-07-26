"""Async GenAI crew-job locks on the TRIP item (propose / suggest-*).

Separate from plan-next-day ``planning_day_index`` so day planning and shorter
crew jobs do not share the same claim fields. Only one of
``planning_day_index`` or ``crew_job_kind`` may be held at a time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from db import keys
from db.protocols import DynamoDBTable
from db.repository.common import (
    ConcurrentModificationError,
    DynamoItem,
    is_conditional_failure,
    now_iso,
    resolve_table,
)
from db.repository.planning import PLANNING_STALE_SECONDS
from db.repository.trips import get_trip_meta

JOB_PROPOSE_CITIES = "propose_cities"
JOB_SUGGEST_CITY = "suggest_city"
JOB_SUGGEST_PLACE = "suggest_place"

CREW_JOB_KINDS = frozenset(
    {JOB_PROPOSE_CITIES, JOB_SUGGEST_CITY, JOB_SUGGEST_PLACE}
)


def clear_stale_crew_job(
    *,
    user_sub: str,
    trip_id: str,
    stale_after_seconds: int = PLANNING_STALE_SECONDS,
    table: DynamoDBTable | None = None,
) -> bool:
    """Clear a stuck ``crew_job_kind`` if ``crew_job_started_at`` is too old."""
    trip = get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=table)
    if not trip or not trip.get("crew_job_kind"):
        return False
    started = str(trip.get("crew_job_started_at") or "").strip()
    if not started:
        return False
    try:
        started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
    except ValueError:
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
                "REMOVE #kind, #started, #day, #baseline, #req "
                "SET #ua = :ua, #err = :err"
            ),
            ExpressionAttributeNames={
                "#kind": "crew_job_kind",
                "#started": "crew_job_started_at",
                "#day": "crew_job_day_index",
                "#baseline": "crew_job_baseline_place_count",
                "#req": "crew_job_request",
                "#ua": "updated_at",
                "#err": "crew_job_error",
            },
            ExpressionAttributeValues={
                ":ua": now_iso(),
                ":err": "Crew job timed out. Please try again.",
                ":expected": trip["crew_job_kind"],
            },
            ConditionExpression="crew_job_kind = :expected",
        )
    except Exception:
        return False
    return True


def claim_crew_job(
    *,
    user_sub: str,
    trip_id: str,
    kind: str,
    day_index: int | None = None,
    baseline_place_count: int | None = None,
    request: dict[str, Any] | None = None,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    """Claim an in-flight GenAI job. Concurrent claimants lose."""
    if kind not in CREW_JOB_KINDS:
        raise ValueError(f"unknown crew job kind: {kind!r}")
    clear_stale_crew_job(user_sub=user_sub, trip_id=trip_id, table=table)
    tbl = resolve_table(table)
    now = now_iso()
    names = {
        "#kind": "crew_job_kind",
        "#started": "crew_job_started_at",
        "#err": "crew_job_error",
        "#ua": "updated_at",
        "#pdi": "planning_day_index",
        "#st": "status",
        "#cands": "suggest_city_candidates",
    }
    values: dict[str, Any] = {
        ":kind": kind,
        ":started": now,
        ":ua": now,
        ":deleting": "deleting",
    }
    set_parts = ["#kind = :kind", "#started = :started", "#ua = :ua"]
    remove_parts = ["#err", "#cands"]

    if day_index is not None:
        names["#day"] = "crew_job_day_index"
        values[":day"] = int(day_index)
        set_parts.append("#day = :day")
    else:
        names["#day"] = "crew_job_day_index"
        remove_parts.append("#day")

    if baseline_place_count is not None:
        names["#baseline"] = "crew_job_baseline_place_count"
        values[":baseline"] = int(baseline_place_count)
        set_parts.append("#baseline = :baseline")
    else:
        names["#baseline"] = "crew_job_baseline_place_count"
        remove_parts.append("#baseline")

    if request is not None:
        names["#req"] = "crew_job_request"
        values[":req"] = request
        set_parts.append("#req = :req")
    else:
        names["#req"] = "crew_job_request"
        remove_parts.append("#req")

    try:
        response = tbl.update_item(
            Key={"pk": keys.user_pk(user_sub), "sk": keys.trip_sk(trip_id)},
            UpdateExpression=(
                f"SET {', '.join(set_parts)} REMOVE {', '.join(remove_parts)}"
            ),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression=(
                "attribute_not_exists(#kind) AND attribute_not_exists(#pdi) "
                "AND #st <> :deleting"
            ),
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if is_conditional_failure(exc):
            raise ConcurrentModificationError(
                "another GenAI job is already in progress for this trip"
            ) from exc
        raise
    return response["Attributes"]


def complete_crew_job(
    *,
    user_sub: str,
    trip_id: str,
    expected_kind: str,
    extra_sets: dict[str, Any] | None = None,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    """Clear in-flight crew job fields after a successful worker write."""
    tbl = resolve_table(table)
    now = now_iso()
    names: dict[str, str] = {
        "#kind": "crew_job_kind",
        "#started": "crew_job_started_at",
        "#err": "crew_job_error",
        "#day": "crew_job_day_index",
        "#baseline": "crew_job_baseline_place_count",
        "#req": "crew_job_request",
        "#ua": "updated_at",
    }
    values: dict[str, Any] = {
        ":ua": now,
        ":expected": expected_kind,
    }
    set_parts = ["#ua = :ua"]
    if extra_sets:
        for i, (key, val) in enumerate(extra_sets.items()):
            alias = f"#x{i}"
            val_alias = f":x{i}"
            names[alias] = key
            values[val_alias] = val
            set_parts.append(f"{alias} = {val_alias}")

    try:
        response = tbl.update_item(
            Key={"pk": keys.user_pk(user_sub), "sk": keys.trip_sk(trip_id)},
            UpdateExpression=(
                f"SET {', '.join(set_parts)} "
                "REMOVE #kind, #started, #err, #day, #baseline, #req"
            ),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="#kind = :expected",
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if is_conditional_failure(exc):
            raise ConcurrentModificationError(
                "crew job claim was lost or changed"
            ) from exc
        raise
    return response["Attributes"]


def fail_crew_job(
    *,
    user_sub: str,
    trip_id: str,
    expected_kind: str,
    error_message: str,
    table: DynamoDBTable | None = None,
) -> DynamoItem | None:
    """Clear claim and record ``crew_job_error``. Returns None if claim already gone."""
    tbl = resolve_table(table)
    try:
        response = tbl.update_item(
            Key={"pk": keys.user_pk(user_sub), "sk": keys.trip_sk(trip_id)},
            UpdateExpression=(
                "SET #err = :err, #ua = :ua "
                "REMOVE #kind, #started, #day, #baseline, #req"
            ),
            ExpressionAttributeNames={
                "#err": "crew_job_error",
                "#ua": "updated_at",
                "#kind": "crew_job_kind",
                "#started": "crew_job_started_at",
                "#day": "crew_job_day_index",
                "#baseline": "crew_job_baseline_place_count",
                "#req": "crew_job_request",
            },
            ExpressionAttributeValues={
                ":err": error_message,
                ":ua": now_iso(),
                ":expected": expected_kind,
            },
            ConditionExpression="#kind = :expected",
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:
        if is_conditional_failure(exc):
            return None
        raise
    return response["Attributes"]
