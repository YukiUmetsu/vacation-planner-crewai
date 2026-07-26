"""Enqueue async plan-next-day worker (Lambda Event invoke or local thread)."""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Callable, Protocol

import boto3

logger = logging.getLogger(__name__)

WORKER_PLAN_NEXT_DAY = "plan_next_day"

EnqueueFn = Callable[[str, str, int], None]


class PlanDayEnqueuer(Protocol):
    def __call__(self, user_sub: str, trip_id: str, day_index: int) -> None: ...


def plan_next_day_async_enabled() -> bool:
    """Async when effective crew mode is agentcore unless env overrides.

    See ``ops.crew_async.plan_day_async_enabled``.
    """
    from ops.crew_async import plan_day_async_enabled

    return plan_day_async_enabled()


def _worker_payload(
    user_sub: str, trip_id: str, day_index: int, *, crew_mode: str
) -> dict[str, Any]:
    return {
        "worker": WORKER_PLAN_NEXT_DAY,
        "user_sub": user_sub,
        "trip_id": trip_id,
        "day_index": day_index,
        "crew_mode": crew_mode,
    }


def _run_local_plan_next_day_worker(
    user_sub: str, trip_id: str, day_index: int, mode: str
) -> None:
    """Background path for local_api (no Lambda Event invoke)."""
    from crews.runner import reset_crew_mode_override, set_crew_mode_override
    from trips.service import TripService

    token = set_crew_mode_override(mode)
    try:
        TripService().execute_plan_next_day(user_sub, trip_id, day_index)
    except Exception:
        logger.exception(
            "local plan_next_day worker failed trip_id=%s day_index=%s",
            trip_id,
            day_index,
        )
    finally:
        reset_crew_mode_override(token)


def enqueue_plan_next_day_worker(user_sub: str, trip_id: str, day_index: int) -> None:
    """Fire-and-forget: Lambda Event invoke in AWS, daemon thread locally."""
    from crews.runner import crew_mode

    mode = crew_mode()
    function_name = os.getenv("AWS_LAMBDA_FUNCTION_NAME", "").strip()
    if function_name:
        client = boto3.client("lambda")
        client.invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=json.dumps(
                _worker_payload(user_sub, trip_id, day_index, crew_mode=mode)
            ).encode("utf-8"),
        )
        logger.info(
            "enqueued plan_next_day worker trip_id=%s day_index=%s crew_mode=%s",
            trip_id,
            day_index,
            mode,
        )
        return

    thread = threading.Thread(
        target=_run_local_plan_next_day_worker,
        args=(user_sub, trip_id, day_index, mode),
        name=f"plan_next_day:{trip_id}:{day_index}",
        daemon=True,
    )
    thread.start()
    logger.info(
        "enqueued local plan_next_day thread trip_id=%s day_index=%s crew_mode=%s",
        trip_id,
        day_index,
        mode,
    )


def is_plan_next_day_worker_event(event: dict[str, Any]) -> bool:
    return (
        isinstance(event, dict)
        and event.get("worker") == WORKER_PLAN_NEXT_DAY
        and bool(event.get("user_sub"))
        and bool(event.get("trip_id"))
        and event.get("day_index") is not None
    )
