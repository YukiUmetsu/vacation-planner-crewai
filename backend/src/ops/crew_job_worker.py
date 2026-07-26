"""Enqueue async crew workers (Lambda Event invoke or local thread)."""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Callable

import boto3

from db.repository.crew_jobs import (
    JOB_PROPOSE_CITIES,
    JOB_SUGGEST_CITY,
    JOB_SUGGEST_PLACE,
)

logger = logging.getLogger(__name__)

WORKER_KINDS = frozenset(
    {JOB_PROPOSE_CITIES, JOB_SUGGEST_CITY, JOB_SUGGEST_PLACE}
)

EnqueueCrewFn = Callable[[dict[str, Any]], None]


def _run_local_crew_worker(payload: dict[str, Any]) -> None:
    from crews.runner import reset_crew_mode_override, set_crew_mode_override
    from trips.service import TripService

    mode = str(payload.get("crew_mode") or "").strip().lower()
    token = set_crew_mode_override(mode) if mode else set_crew_mode_override(None)
    kind = str(payload.get("worker") or "")
    user_sub = str(payload["user_sub"])
    trip_id = str(payload["trip_id"])
    service = TripService()
    try:
        if kind == JOB_PROPOSE_CITIES:
            service.execute_propose_cities(user_sub, trip_id)
        elif kind == JOB_SUGGEST_CITY:
            service.execute_suggest_city(user_sub, trip_id)
        elif kind == JOB_SUGGEST_PLACE:
            day_index = int(payload["day_index"])
            service.execute_suggest_place(user_sub, trip_id, day_index)
        else:
            logger.error("unknown local crew worker kind=%s", kind)
    except Exception:
        logger.exception(
            "local crew worker failed kind=%s trip_id=%s",
            kind,
            trip_id,
        )
    finally:
        reset_crew_mode_override(token)


def enqueue_crew_job_worker(payload: dict[str, Any]) -> None:
    """Fire-and-forget: Lambda Event invoke in AWS, daemon thread locally."""
    kind = str(payload.get("worker") or "")
    if kind not in WORKER_KINDS:
        raise ValueError(f"unknown crew worker kind: {kind!r}")
    if not payload.get("user_sub") or not payload.get("trip_id"):
        raise ValueError("crew worker payload requires user_sub and trip_id")

    from crews.runner import crew_mode

    body = {**payload, "crew_mode": payload.get("crew_mode") or crew_mode()}
    function_name = os.getenv("AWS_LAMBDA_FUNCTION_NAME", "").strip()
    if function_name:
        client = boto3.client("lambda")
        client.invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=json.dumps(body).encode("utf-8"),
        )
        logger.info(
            "enqueued crew worker kind=%s trip_id=%s crew_mode=%s",
            kind,
            body.get("trip_id"),
            body.get("crew_mode"),
        )
        return

    thread = threading.Thread(
        target=_run_local_crew_worker,
        args=(body,),
        name=f"crew:{kind}:{body.get('trip_id')}",
        daemon=True,
    )
    thread.start()
    logger.info(
        "enqueued local crew thread kind=%s trip_id=%s crew_mode=%s",
        kind,
        body.get("trip_id"),
        body.get("crew_mode"),
    )


def is_crew_job_worker_event(event: dict[str, Any]) -> bool:
    return (
        isinstance(event, dict)
        and event.get("worker") in WORKER_KINDS
        and bool(event.get("user_sub"))
        and bool(event.get("trip_id"))
    )
