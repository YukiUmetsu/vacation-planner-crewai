"""Structured SAFETY_METRIC logs (no traveler/AI text payloads)."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def log_safety_metric(
    *,
    direction: str,
    source: str,
    mode: str,
    intervened: bool,
    trip_id: str | None = None,
    safety_latency_ms: int | None = None,
    output_mode: str | None = None,
    unavailable: bool = False,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit one searchable safety line — never include full user/AI strings."""
    payload: dict[str, Any] = {
        "event": "safety_check",
        "direction": direction,
        "source": source,
        "mode": mode,
        "intervened": intervened,
    }
    if trip_id:
        payload["trip_id"] = trip_id
    if safety_latency_ms is not None:
        payload["safety_latency_ms"] = safety_latency_ms
    if output_mode:
        payload["output_mode"] = output_mode
    if unavailable:
        payload["unavailable"] = True
    if extra:
        for key, value in extra.items():
            if value is not None:
                payload[key] = value
    logger.info(
        "SAFETY_METRIC %s", json.dumps(payload, ensure_ascii=False, default=str)
    )
