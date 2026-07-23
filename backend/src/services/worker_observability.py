"""Structured outcomes for the plan-next-day Event worker (ops / CloudWatch)."""

from __future__ import annotations

import logging
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
