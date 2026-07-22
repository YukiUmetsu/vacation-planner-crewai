"""Parse BFF → AgentCore invoke body into (crew_name, inputs)."""

from __future__ import annotations

from typing import Any, Literal

CrewName = Literal["day_plan", "city_route", "suggest_place"]
ALLOWED_CREWS = frozenset({"day_plan", "city_route", "suggest_place"})


class PayloadError(ValueError):
    """Invalid invoke payload."""


def parse_invoke_payload(raw: Any) -> tuple[CrewName, dict[str, Any]]:
    """
    Expected shape:
      { "crew": "day_plan" | "city_route" | "suggest_place", "inputs": { ... } }

    Also accepts a wrapped body: { "payload": { ... } }.
    """
    if not isinstance(raw, dict):
        raise PayloadError("payload must be a JSON object")

    body = raw.get("payload") if isinstance(raw.get("payload"), dict) else raw

    crew = body.get("crew")
    if crew not in ALLOWED_CREWS:
        raise PayloadError(
            f"crew must be one of {sorted(ALLOWED_CREWS)}, got {crew!r}"
        )

    inputs = body.get("inputs")
    if not isinstance(inputs, dict):
        raise PayloadError("inputs must be a JSON object")

    return crew, inputs  # type: ignore[return-value]
