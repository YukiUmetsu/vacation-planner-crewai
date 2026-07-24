"""Persistence for offline eval metrics (dedicated DynamoDB table)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key

from db.client import get_metrics_table
from db.metrics_keys import (
    case_sk,
    case_sk_prefix,
    eval_pk,
    evt_gsi1_pk,
    exp_gsi1_pk,
    online_event_sk,
    online_exp_gsi1_pk,
    online_product_pk,
    online_quality_pk,
    run_gsi1_sk,
    run_sk,
)
from db.protocols import DynamoDBTable
from db.repository.common import prepare_dynamo_item
from db.safe_table import ensure_safe_table
from db.schema import GSI1_NAME


def resolve_metrics_table(table: DynamoDBTable | None) -> DynamoDBTable:
    return ensure_safe_table(table if table is not None else get_metrics_table())


def _to_plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {k: _to_plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_plain(v) for v in value]
    return value


def _public_run(item: dict[str, Any]) -> dict[str, Any]:
    plain = _to_plain(item)
    return {
        "run_id": plain.get("run_id"),
        "started_at": plain.get("started_at"),
        "experiment_key": plain.get("experiment_key"),
        "dimensions": plain.get("dimensions") or {},
        "aggregates": plain.get("aggregates") or {},
        "case_count": plain.get("case_count"),
        "passed_count": plain.get("passed_count"),
        "updated_at": plain.get("updated_at"),
    }


def _public_case(item: dict[str, Any]) -> dict[str, Any]:
    plain = _to_plain(item)
    return {
        "case_id": plain.get("case_id"),
        "passed": bool(plain.get("passed")),
        "failures": list(plain.get("failures") or []),
        "metrics": plain.get("metrics") or {},
        "run_id": plain.get("run_id"),
        "started_at": plain.get("started_at"),
        "experiment_key": plain.get("experiment_key"),
    }


def put_eval_run(
    *,
    run_id: str,
    started_at: str,
    experiment_key: str,
    dimensions: dict[str, Any],
    aggregates: dict[str, float],
    case_count: int,
    passed_count: int,
    updated_at: str,
    table: DynamoDBTable | None = None,
) -> dict[str, Any]:
    if (
        not run_id
        or not started_at
        or not experiment_key
        or "#" in run_id
        or "#" in started_at
        or "#" in experiment_key
    ):
        raise ValueError(
            "run_id/started_at/experiment_key must be non-empty and contain no '#'"
        )
    tbl = resolve_metrics_table(table)
    item = prepare_dynamo_item(
        {
            "pk": eval_pk(),
            "sk": run_sk(started_at, run_id),
            "gsi1pk": exp_gsi1_pk(experiment_key),
            "gsi1sk": run_gsi1_sk(started_at, run_id),
            "entity_type": "METRICS_EVAL_RUN",
            "run_id": run_id,
            "started_at": started_at,
            "experiment_key": experiment_key,
            "dimensions": dimensions,
            "aggregates": aggregates,
            "case_count": case_count,
            "passed_count": passed_count,
            "updated_at": updated_at,
        }
    )
    tbl.put_item(Item=item)
    return _public_run(item)


def put_eval_case(
    *,
    run_id: str,
    started_at: str,
    experiment_key: str,
    case_id: str,
    passed: bool,
    failures: list[str],
    metrics: dict[str, Any],
    table: DynamoDBTable | None = None,
) -> dict[str, Any]:
    """Persist a case row. Cases are not written to GSI1 (runs-only index)."""
    if (
        not case_id
        or not run_id
        or not started_at
        or "#" in case_id
        or "#" in run_id
        or "#" in started_at
    ):
        raise ValueError("case_id/run_id/started_at must be non-empty and contain no '#'")
    tbl = resolve_metrics_table(table)
    item = prepare_dynamo_item(
        {
            "pk": eval_pk(),
            "sk": case_sk(started_at, run_id, case_id),
            "entity_type": "METRICS_EVAL_CASE",
            "run_id": run_id,
            "started_at": started_at,
            "experiment_key": experiment_key,
            "case_id": case_id,
            "passed": passed,
            "failures": failures,
            "metrics": metrics,
        }
    )
    tbl.put_item(Item=item)
    return _public_case(item)


def list_eval_runs(
    *,
    experiment_key: str | None = None,
    limit: int = 50,
    table: DynamoDBTable | None = None,
) -> list[dict[str, Any]]:
    tbl = resolve_metrics_table(table)
    limit = max(1, min(int(limit), 200))
    if experiment_key:
        # GSI holds run items only — Limit maps 1:1 to returned runs.
        resp = tbl.query(
            IndexName=GSI1_NAME,
            KeyConditionExpression=Key("gsi1pk").eq(exp_gsi1_pk(experiment_key)),
            ScanIndexForward=False,
            Limit=limit,
        )
    else:
        resp = tbl.query(
            KeyConditionExpression=Key("pk").eq(eval_pk())
            & Key("sk").begins_with("RUN#"),
            ScanIndexForward=False,
            Limit=limit,
        )
    runs: list[dict[str, Any]] = []
    for item in resp.get("Items") or []:
        if item.get("entity_type") != "METRICS_EVAL_RUN":
            continue
        runs.append(_public_run(item))
    return runs


def _query_all_cases(
    tbl: DynamoDBTable, *, started_at: str, run_id: str
) -> list[dict[str, Any]]:
    prefix = case_sk_prefix(started_at, run_id)
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": Key("pk").eq(eval_pk())
        & Key("sk").begins_with(prefix),
    }
    while True:
        case_resp = tbl.query(**kwargs)
        for c in case_resp.get("Items") or []:
            if c.get("entity_type") == "METRICS_EVAL_CASE":
                items.append(_public_case(c))
        last = case_resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return items


def get_eval_run(
    *,
    run_id: str,
    started_at: str,
    include_cases: bool = True,
    table: DynamoDBTable | None = None,
) -> dict[str, Any] | None:
    tbl = resolve_metrics_table(table)
    resp = tbl.get_item(Key={"pk": eval_pk(), "sk": run_sk(started_at, run_id)})
    item = resp.get("Item")
    if not item or item.get("entity_type") != "METRICS_EVAL_RUN":
        return None
    out = _public_run(item)
    if include_cases:
        out["cases"] = _query_all_cases(tbl, started_at=started_at, run_id=run_id)
    return out


def _public_online_quality(item: dict[str, Any]) -> dict[str, Any]:
    plain = _to_plain(item)
    return {
        "event_id": plain.get("event_id"),
        "occurred_at": plain.get("occurred_at"),
        "experiment_key": plain.get("experiment_key"),
        "trip_id": plain.get("trip_id"),
        "day_index": plain.get("day_index"),
        "passes_relevance": plain.get("passes_relevance"),
        "relevance_score": plain.get("relevance_score"),
        "constraint_score": plain.get("constraint_score"),
        "failure_tags": list(plain.get("failure_tags") or []),
        "guardrail_code": plain.get("guardrail_code"),
        "places_count": plain.get("places_count"),
        "crew_name": plain.get("crew_name"),
        "prompt_version": plain.get("prompt_version"),
        "prompt_hash": plain.get("prompt_hash"),
        "model_id": plain.get("model_id"),
        "git_sha": plain.get("git_sha"),
        "input_context_chars": plain.get("input_context_chars"),
        "context_was_slimmed": plain.get("context_was_slimmed"),
        "output_schema_version": plain.get("output_schema_version"),
    }


def _public_online_product(item: dict[str, Any]) -> dict[str, Any]:
    plain = _to_plain(item)
    return {
        "event_id": plain.get("event_id"),
        "occurred_at": plain.get("occurred_at"),
        "event_name": plain.get("event_name"),
        "user_sub_hash": plain.get("user_sub_hash"),
        "trip_id": plain.get("trip_id"),
        "day_index": plain.get("day_index"),
        "payload": plain.get("payload") or {},
    }


def put_online_quality_event(
    *,
    event_id: str,
    occurred_at: str,
    payload: dict[str, Any],
    experiment_key: str | None = None,
    table: DynamoDBTable | None = None,
) -> dict[str, Any]:
    if (
        not event_id
        or not occurred_at
        or "#" in event_id
        or "#" in occurred_at
        or (experiment_key is not None and (not experiment_key or "#" in experiment_key))
    ):
        raise ValueError(
            "event_id/occurred_at must be non-empty and contain no '#'; "
            "experiment_key when set must be non-empty and contain no '#'"
        )
    tbl = resolve_metrics_table(table)
    # Payload first, then reserved keys. Always clear GSI attrs from payload so
    # callers cannot inject gsi1pk/gsi1sk when experiment_key is absent.
    item: dict[str, Any] = {
        **payload,
        "pk": online_quality_pk(),
        "sk": online_event_sk(occurred_at, event_id),
        "entity_type": "METRICS_ONLINE_QUALITY",
        "event_id": event_id,
        "occurred_at": occurred_at,
    }
    item.pop("gsi1pk", None)
    item.pop("gsi1sk", None)
    item.pop("experiment_key", None)
    if experiment_key:
        item["experiment_key"] = experiment_key
        item["gsi1pk"] = online_exp_gsi1_pk(experiment_key)
        item["gsi1sk"] = online_event_sk(occurred_at, event_id)
    prepared = prepare_dynamo_item(item)
    tbl.put_item(Item=prepared)
    return _public_online_quality(prepared)


def put_online_product_event(
    *,
    event_id: str,
    occurred_at: str,
    event_name: str,
    user_sub_hash: str,
    trip_id: str | None = None,
    day_index: int | None = None,
    payload: dict[str, Any] | None = None,
    table: DynamoDBTable | None = None,
) -> dict[str, Any]:
    if (
        not event_id
        or not occurred_at
        or not event_name
        or "#" in event_id
        or "#" in occurred_at
        or "#" in event_name
    ):
        raise ValueError(
            "event_id/occurred_at/event_name must be non-empty and contain no '#'"
        )
    tbl = resolve_metrics_table(table)
    item = prepare_dynamo_item(
        {
            "pk": online_product_pk(),
            "sk": online_event_sk(occurred_at, event_id),
            "gsi1pk": evt_gsi1_pk(event_name),
            "gsi1sk": online_event_sk(occurred_at, event_id),
            "entity_type": "METRICS_ONLINE_PRODUCT",
            "event_id": event_id,
            "occurred_at": occurred_at,
            "event_name": event_name,
            "user_sub_hash": user_sub_hash,
            "trip_id": trip_id,
            "day_index": day_index,
            "payload": payload or {},
        }
    )
    tbl.put_item(Item=item)
    return _public_online_product(item)


def list_online_events(
    *,
    kind: str,
    experiment_key: str | None = None,
    event_name: str | None = None,
    limit: int = 50,
    table: DynamoDBTable | None = None,
) -> list[dict[str, Any]]:
    """List recent online metrics. ``kind`` is ``quality`` or ``product``."""
    kind_norm = kind.strip().lower()
    if kind_norm not in {"quality", "product"}:
        raise ValueError("kind must be 'quality' or 'product'")
    tbl = resolve_metrics_table(table)
    limit = max(1, min(int(limit), 200))

    if kind_norm == "quality":
        entity = "METRICS_ONLINE_QUALITY"
        public = _public_online_quality
        if experiment_key:
            resp = tbl.query(
                IndexName=GSI1_NAME,
                KeyConditionExpression=Key("gsi1pk").eq(
                    online_exp_gsi1_pk(experiment_key)
                ),
                ScanIndexForward=False,
                Limit=limit,
            )
        else:
            resp = tbl.query(
                KeyConditionExpression=Key("pk").eq(online_quality_pk())
                & Key("sk").begins_with("TS#"),
                ScanIndexForward=False,
                Limit=limit,
            )
    else:
        entity = "METRICS_ONLINE_PRODUCT"
        public = _public_online_product
        if event_name:
            resp = tbl.query(
                IndexName=GSI1_NAME,
                KeyConditionExpression=Key("gsi1pk").eq(evt_gsi1_pk(event_name)),
                ScanIndexForward=False,
                Limit=limit,
            )
        else:
            resp = tbl.query(
                KeyConditionExpression=Key("pk").eq(online_product_pk())
                & Key("sk").begins_with("TS#"),
                ScanIndexForward=False,
                Limit=limit,
            )

    out: list[dict[str, Any]] = []
    for item in resp.get("Items") or []:
        if item.get("entity_type") != entity:
            continue
        out.append(public(item))
        if len(out) >= limit:
            break
    return out
