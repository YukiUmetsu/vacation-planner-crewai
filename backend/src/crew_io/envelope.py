"""Unwrap CrewEnvelope vs legacy bare DayPlan / CityRoute / Place payloads."""

from __future__ import annotations

from typing import Any


def unwrap_crew_payload(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    """Return ``(result, quality|None, invocation|None)``.

    Accepts:
    - CrewEnvelope: ``{result, quality?, invocation?}``
    - Legacy bare domain dict (DayPlan / CityRoute / Place)
    """
    if not isinstance(payload, dict):
        raise TypeError(f"crew payload must be a dict, got {type(payload).__name__}")

    result = payload.get("result")
    if isinstance(result, dict) and (
        "invocation" in payload or "quality" in payload or "result" in payload
    ):
        # Envelope: prefer when ``result`` is a nested domain object.
        # Bare DayPlan never has a nested ``result`` key.
        quality = payload.get("quality")
        invocation = payload.get("invocation")
        return (
            result,
            quality if isinstance(quality, dict) else None,
            invocation if isinstance(invocation, dict) else None,
        )

    return payload, None, None
