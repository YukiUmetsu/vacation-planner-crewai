"""Parse BFF → AgentCore invoke body into (crew_name, inputs)."""

from __future__ import annotations

import os
from typing import Any, Literal

CrewName = Literal[
    "day_plan", "day_plan_single", "city_route", "suggest_place", "suggest_city"
]

# Production BFF crews. day_plan_single is eval-only unless explicitly enabled.
_PROD_CREWS = frozenset(
    {
        "day_plan",
        "city_route",
        "suggest_place",
        "suggest_city",
    }
)
_EVAL_CREWS = frozenset({"day_plan_single"})


def _allow_eval_crews() -> bool:
    raw = os.getenv("ALLOW_EVAL_CREWS", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def allowed_crews() -> frozenset[str]:
    if _allow_eval_crews():
        return _PROD_CREWS | _EVAL_CREWS
    return _PROD_CREWS


# Back-compat name for docs; always call allowed_crews() at runtime (env-sensitive).
ALLOWED_CREWS = _PROD_CREWS


class PayloadError(ValueError):
    """Invalid invoke payload."""


def parse_invoke_payload(raw: Any) -> tuple[CrewName, dict[str, Any]]:
    """
    Expected shape:
      { "crew": "day_plan" | "city_route" | "suggest_place" | "suggest_city", "inputs": { ... } }

    Also accepts a wrapped body: { "payload": { ... } }.

    ``day_plan_single`` is accepted only when ALLOW_EVAL_CREWS=1 (offline evals).
    """
    if not isinstance(raw, dict):
        raise PayloadError("payload must be a JSON object")

    body = raw.get("payload") if isinstance(raw.get("payload"), dict) else raw

    crews = allowed_crews()
    crew = body.get("crew")
    if crew not in crews:
        raise PayloadError(
            f"crew must be one of {sorted(crews)}, got {crew!r}"
        )

    inputs = body.get("inputs")
    if not isinstance(inputs, dict):
        raise PayloadError("inputs must be a JSON object")

    return crew, inputs  # type: ignore[return-value]
