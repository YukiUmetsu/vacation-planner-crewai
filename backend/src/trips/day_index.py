"""Pure day-index helpers shared by plan-day and day edits.

Kept out of the plan-day jobs/pipeline modules so suggest/mutations/status do
not import the plan-next-day orchestration graph.
"""

from __future__ import annotations

from typing import Any

from http_utils import ApiError


def first_missing_day_index(
    days: list[dict[str, Any]], day_count: int
) -> int | None:
    """Lowest 1-based day_index with no DAY row, or None when the trip is full."""
    planned = {
        int(d.get("day_index") or 0)
        for d in days
        if int(d.get("day_index") or 0) >= 1
    }
    for index in range(1, day_count + 1):
        if index not in planned:
            return index
    return None


def resolve_plan_day_index(
    *,
    trip: dict[str, Any],
    days: list[dict[str, Any]],
) -> int:
    """Day to plan next — fill gaps before trusting a jumped ``next_day_index``."""
    day_count = int(trip["day_count"])
    gap = first_missing_day_index(days, day_count)
    if gap is None:
        raise ApiError(409, "all days already planned", code="complete")
    return gap
