"""Day-plan edits facade (ADR 005 compatibility).

Re-exports suggest / remove / reorder / delete and ``status_after_day_edit`` so
``TripService`` and existing imports stay stable. Implementation lives in
``trips.suggest_place``, ``trips.day_mutations``, and ``trips.day_status``.
"""

from __future__ import annotations

from trips.day_mutations import delete_day, remove_place, reorder_place
from trips.day_status import status_after_day_edit
from trips.suggest_place import (
    execute_suggest_place,
    suggest_place,
    start_suggest_place,
)

__all__ = [
    "status_after_day_edit",
    "suggest_place",
    "start_suggest_place",
    "execute_suggest_place",
    "remove_place",
    "reorder_place",
    "delete_day",
]
