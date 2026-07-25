"""Enqueue async plan-next-day worker (Lambda Event invoke)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Protocol

import boto3

logger = logging.getLogger(__name__)

WORKER_PLAN_NEXT_DAY = "plan_next_day"

EnqueueFn = Callable[[str, str, int], None]


class PlanDayEnqueuer(Protocol):
    def __call__(self, user_sub: str, trip_id: str, day_index: int) -> None: ...


def plan_next_day_async_enabled() -> bool:
    """Async when CREW_MODE=agentcore unless PLAN_NEXT_DAY_ASYNC overrides.

    Request-scoped ``X-Crew-Mode`` overrides (AUTH_MODE=dev) force **sync** so the
    worker never runs under a different mode than the HTTP request that claimed it.
    """
    from crews.runner import has_crew_mode_override

    if has_crew_mode_override():
        return False

    flag = os.getenv("PLAN_NEXT_DAY_ASYNC", "auto").strip().lower()
    if flag in {"off", "0", "false", "no", "sync"}:
        return False
    if flag in {"on", "1", "true", "yes", "async"}:
        return True
    # auto — use effective crew_mode (env) since override already returned above
    from crews.runner import crew_mode

    return crew_mode() == "agentcore"


def enqueue_plan_next_day_worker(user_sub: str, trip_id: str, day_index: int) -> None:
    """Fire-and-forget invoke of this Lambda as a worker."""
    function_name = os.getenv("AWS_LAMBDA_FUNCTION_NAME", "").strip()
    if not function_name:
        raise RuntimeError(
            "AWS_LAMBDA_FUNCTION_NAME unset; cannot enqueue plan-next-day worker"
        )
    payload = {
        "worker": WORKER_PLAN_NEXT_DAY,
        "user_sub": user_sub,
        "trip_id": trip_id,
        "day_index": day_index,
    }
    client = boto3.client("lambda")
    client.invoke(
        FunctionName=function_name,
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    logger.info(
        "enqueued plan_next_day worker trip_id=%s day_index=%s",
        trip_id,
        day_index,
    )


def is_plan_next_day_worker_event(event: dict[str, Any]) -> bool:
    return (
        isinstance(event, dict)
        and event.get("worker") == WORKER_PLAN_NEXT_DAY
        and bool(event.get("user_sub"))
        and bool(event.get("trip_id"))
        and event.get("day_index") is not None
    )
