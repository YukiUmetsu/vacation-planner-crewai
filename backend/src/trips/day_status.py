"""Status / next_day_index helpers after itinerary edits.

Per ADR 005: leaf helper — no TripService import. Used by day mutations and
route reconfirm (so ``db`` need not import ``trips.day_edit``).
"""

from __future__ import annotations

from typing import Any

from trips.day_index import first_missing_day_index


def status_after_day_edit(
    *,
    remaining_days: list[dict[str, Any]],
    day_count: int,
    previous_status: str,
) -> tuple[int, str]:
    """Return (next_day_index, status) after a day was removed or emptied."""
    gap = first_missing_day_index(remaining_days, day_count)
    if gap is None:
        return day_count + 1, "complete"
    if not remaining_days:
        # Route is still confirmed; traveler can plan again from day 1.
        if previous_status in {"planning", "complete", "failed"}:
            return 1, "routing_confirmed"
        return 1, previous_status or "routing_confirmed"
    return gap, "planning"

