"""Scoring hooks for offline evals.

LEARNING: replace the stub bodies with real checks (schema, place_key,
already_visited overlap, place count bounds, etc.). Return a list of
human-readable failure strings; empty list means pass.
"""

from __future__ import annotations

from typing import Any

from evals.case import EvalCase


def score_day_plan(output: dict[str, Any], case: EvalCase) -> list[str]:
    """Return failure messages for a ``day_plan`` crew output."""
    _ = output
    if case.expected:
        return [
            "LEARNING: implement score_day_plan "
            f"(fixture {case.id!r} declares expected={sorted(case.expected)})"
        ]
    return []


def score_city_route(output: dict[str, Any], case: EvalCase) -> list[str]:
    """Return failure messages for a ``city_route`` crew output."""
    _ = output
    if case.expected:
        return [
            "LEARNING: implement score_city_route "
            f"(fixture {case.id!r} declares expected={sorted(case.expected)})"
        ]
    return []


def score_output(output: dict[str, Any], case: EvalCase) -> list[str]:
    if case.crew == "day_plan":
        return score_day_plan(output, case)
    return score_city_route(output, case)
