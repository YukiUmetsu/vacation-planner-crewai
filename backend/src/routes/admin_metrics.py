"""Private admin metrics API (Cognito sub allowlist)."""

from __future__ import annotations

import os
from typing import Any

from db import repository as repo
from http_utils import ApiError


def metrics_admin_subs() -> set[str]:
    raw = os.getenv("METRICS_ADMIN_SUBS", "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def require_metrics_admin(user_sub: str) -> None:
    allowed = metrics_admin_subs()
    if not allowed or user_sub not in allowed:
        raise ApiError(403, "metrics admin access required", code="forbidden")


def _query_params(event: dict[str, Any]) -> dict[str, str]:
    raw = event.get("queryStringParameters") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            continue
        # local_http may pass multi-value lists; API Gateway uses a single string.
        if isinstance(value, list):
            if not value:
                continue
            value = value[0]
        out[str(key)] = str(value)
    return out


def _reject_key_metacharacters(label: str, value: str) -> str:
    """Keep DynamoDB key segments free of ``#`` (our key delimiter)."""
    cleaned = value.strip()
    if not cleaned or "#" in cleaned:
        raise ApiError(
            400,
            f"invalid {label}",
            code="invalid_query",
        )
    return cleaned


def list_runs(event: dict[str, Any], user_sub: str) -> dict[str, Any]:
    require_metrics_admin(user_sub)
    qs = _query_params(event)
    experiment_key = (qs.get("experiment_key") or "").strip() or None
    if experiment_key is not None:
        experiment_key = _reject_key_metacharacters("experiment_key", experiment_key)
    try:
        limit = int(qs.get("limit") or "50")
    except ValueError as exc:
        raise ApiError(400, "limit must be an integer", code="invalid_query") from exc
    runs = repo.list_eval_runs(experiment_key=experiment_key, limit=limit)
    return {"runs": runs}


def get_run(event: dict[str, Any], user_sub: str, run_id: str) -> dict[str, Any]:
    require_metrics_admin(user_sub)
    run_id = _reject_key_metacharacters("run_id", run_id)
    qs = _query_params(event)
    started_at = _reject_key_metacharacters(
        "started_at", qs.get("started_at") or ""
    )
    include_cases = (qs.get("include_cases") or "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    run = repo.get_eval_run(
        run_id=run_id,
        started_at=started_at,
        include_cases=include_cases,
    )
    if not run:
        raise ApiError(404, f"eval run not found: {run_id}", code="not_found")
    return run


def list_online(event: dict[str, Any], user_sub: str) -> dict[str, Any]:
    require_metrics_admin(user_sub)
    qs = _query_params(event)
    kind = (qs.get("kind") or "quality").strip().lower()
    if kind not in {"quality", "product"}:
        raise ApiError(
            400,
            "kind must be 'quality' or 'product'",
            code="invalid_query",
        )
    experiment_key = (qs.get("experiment_key") or "").strip() or None
    event_name = (qs.get("event_name") or "").strip() or None
    if experiment_key is not None:
        experiment_key = _reject_key_metacharacters("experiment_key", experiment_key)
    if event_name is not None:
        event_name = _reject_key_metacharacters("event_name", event_name)
    try:
        limit = int(qs.get("limit") or "50")
    except ValueError as exc:
        raise ApiError(400, "limit must be an integer", code="invalid_query") from exc
    try:
        events = repo.list_online_events(
            kind=kind,
            experiment_key=experiment_key if kind == "quality" else None,
            event_name=event_name if kind == "product" else None,
            limit=limit,
        )
    except ValueError as exc:
        raise ApiError(400, str(exc), code="invalid_query") from exc
    return {"kind": kind, "events": events}
