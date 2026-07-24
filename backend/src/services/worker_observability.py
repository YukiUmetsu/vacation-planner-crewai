"""Structured outcomes for the plan-next-day Event worker (ops / CloudWatch)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
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


def log_quality_metrics(
    *,
    trip_id: str,
    day_index: int,
    quality: dict[str, Any] | None,
    invocation: dict[str, Any] | None,
    guardrail_code: str | None = None,
    places_count: int | None = None,
) -> None:
    """CloudWatch-searchable quality + invocation line (no place payloads / PII)."""
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
        "git_sha": inv.get("git_sha"),
        "input_context_chars": inv.get("input_context_chars"),
        "context_was_slimmed": inv.get("context_was_slimmed"),
        "output_schema_version": inv.get("output_schema_version"),
    }
    logger.info(
        "QUALITY_METRIC %s", json.dumps(payload, ensure_ascii=False, default=str)
    )


def stable_user_sub_hash(user_sub: str) -> str:
    """Stable, non-reversible user id for product metrics (not Python hash())."""
    pepper = (
        os.getenv("PRODUCT_METRICS_HASH_PEPPER", "").strip()
        or "vacation-planner-product-metrics-v1"
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
