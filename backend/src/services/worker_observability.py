"""Structured outcomes for the plan-next-day Event worker (ops / CloudWatch).

Online quality/product events dual-write to CloudWatch logs and the metrics
DynamoDB table. Dynamo failures are soft-failed so trip/events paths stay up.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def log_worker_outcome(
    *,
    trip_id: str,
    day_index: int,
    outcome: str,
    duration_ms: int,
    retryable: bool | None = None,
    error_code: str | None = None,
    error_type: str | None = None,
) -> None:
    """Emit one searchable line per worker attempt (no PII / crew payloads)."""
    parts = [
        "plan_next_day_worker",
        f"outcome={outcome}",
        f"trip_id={trip_id}",
        f"day_index={day_index}",
        f"duration_ms={duration_ms}",
    ]
    if retryable is not None:
        parts.append(f"retryable={str(retryable).lower()}")
    if error_code:
        parts.append(f"error_code={error_code}")
    if error_type:
        parts.append(f"error_type={error_type}")
    logger.info(" ".join(parts))


class WorkerTimer:
    """Wall-clock timer for worker duration_ms."""

    def __init__(self) -> None:
        self._start = time.perf_counter()

    def duration_ms(self) -> int:
        return max(0, int((time.perf_counter() - self._start) * 1000))


def log_crew_duration(
    *,
    operation: str,
    trip_id: str,
    duration_ms: int,
    extra: dict[str, Any] | None = None,
) -> None:
    """Log sync crew call duration (e.g. propose-cities) for gateway-timeout watch."""
    parts = [
        operation,
        f"trip_id={trip_id}",
        f"duration_ms={duration_ms}",
    ]
    if extra:
        for key, value in extra.items():
            parts.append(f"{key}={value}")
    logger.info(" ".join(parts))


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def online_quality_experiment_key(payload: dict[str, Any]) -> str | None:
    """Fingerprint invocation dims for fair online quality filtering."""
    dims = {
        "prompt_version": payload.get("prompt_version") or "",
        "prompt_hash": payload.get("prompt_hash") or "",
        "model_id": payload.get("model_id") or "",
        "git_sha": payload.get("git_sha") or "",
        "crew_name": payload.get("crew_name") or "",
    }
    if not any(dims.values()):
        return None
    return hashlib.sha256(_canonical_json(dims).encode("utf-8")).hexdigest()[:16]


def _persist_online_quality(payload: dict[str, Any]) -> None:
    try:
        from db import repository as repo

        event_id = uuid.uuid4().hex[:12]
        occurred_at = _utc_now_iso()
        exp_key = online_quality_experiment_key(payload)
        repo.put_online_quality_event(
            event_id=event_id,
            occurred_at=occurred_at,
            payload=payload,
            experiment_key=exp_key,
        )
    except Exception as exc:  # noqa: BLE001 — never break planning on metrics I/O
        logger.warning(
            "metrics DynamoDB quality persist failed: %s: %s",
            type(exc).__name__,
            exc,
        )


def _persist_online_product(body: dict[str, Any]) -> None:
    try:
        from db import repository as repo

        event_id = uuid.uuid4().hex[:12]
        occurred_at = _utc_now_iso()
        repo.put_online_product_event(
            event_id=event_id,
            occurred_at=occurred_at,
            event_name=str(body.get("event_name") or ""),
            user_sub_hash=str(body.get("user_sub_hash") or ""),
            trip_id=body.get("trip_id"),
            day_index=body.get("day_index"),
            payload=body.get("payload") if isinstance(body.get("payload"), dict) else {},
        )
    except Exception as exc:  # noqa: BLE001 — never break product events on metrics I/O
        logger.warning(
            "metrics DynamoDB product persist failed: %s: %s",
            type(exc).__name__,
            exc,
        )


def log_quality_metrics(
    *,
    trip_id: str,
    day_index: int,
    quality: dict[str, Any] | None,
    invocation: dict[str, Any] | None,
    guardrail_code: str | None = None,
    places_count: int | None = None,
) -> None:
    """CloudWatch + DynamoDB quality + invocation line (no place payloads / PII)."""
    q = quality or {}
    inv = invocation or {}
    tags = q.get("failure_tags") if isinstance(q.get("failure_tags"), list) else []
    payload = {
        "event": "plan_day_quality",
        "trip_id": trip_id,
        "day_index": day_index,
        "passes_relevance": q.get("passes_relevance"),
        "relevance_score": q.get("relevance_score"),
        "constraint_score": q.get("constraint_score"),
        "failure_tags": tags,
        "guardrail_code": guardrail_code,
        "places_count": places_count,
        "crew_name": inv.get("crew_name"),
        "prompt_version": inv.get("prompt_version"),
        "prompt_hash": inv.get("prompt_hash"),
        "model_id": inv.get("model_id"),
        "git_sha": inv.get("git_sha") or os.getenv("BACKEND_GIT_SHA", ""),
        "backend_git_sha": os.getenv("BACKEND_GIT_SHA", "") or None,
        "input_context_chars": inv.get("input_context_chars"),
        "context_was_slimmed": inv.get("context_was_slimmed"),
        "output_schema_version": inv.get("output_schema_version"),
    }
    if payload["backend_git_sha"] is None:
        payload.pop("backend_git_sha")

    logger.info(
        "QUALITY_METRIC %s", json.dumps(payload, ensure_ascii=False, default=str)
    )
    _persist_online_quality(payload)


def stable_user_sub_hash(user_sub: str) -> str:
    """Stable, non-reversible user id for product metrics (not Python hash())."""
    from services.secrets import resolve_secret

    pepper = resolve_secret(
        plain_env="PRODUCT_METRICS_HASH_PEPPER",
        arn_env="PRODUCT_METRICS_PEPPER_SECRET_ARN",
        fallback="vacation-planner-product-metrics-v1",
    )
    digest = hashlib.sha256(f"{pepper}:{user_sub}".encode("utf-8")).hexdigest()
    return digest[:16]


def log_product_event(
    *,
    event_name: str,
    user_sub: str,
    trip_id: str | None = None,
    day_index: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Online product analytics event (allowlisted names only at the route layer)."""
    body = {
        "event": "product_metric",
        "event_name": event_name,
        "user_sub_hash": stable_user_sub_hash(user_sub),
        "trip_id": trip_id,
        "day_index": day_index,
        "payload": payload or {},
    }
    logger.info("PRODUCT_METRIC %s", json.dumps(body, ensure_ascii=False, default=str))
    _persist_online_product(body)
