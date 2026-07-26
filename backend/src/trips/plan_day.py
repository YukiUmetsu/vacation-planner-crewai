"""Compatibility facade for plan-next-day (ADR 005).

Prefer ``trips.plan_day_api`` for new call sites. This module re-exports the
same public functions so older ``from trips import plan_day`` imports keep
working.

Implementation map:

- ``plan_day_api`` — public entrypoints
- ``plan_day_jobs`` — claim / async worker / sync orchestration
- ``plan_day_agent_pipeline`` — crew → quality → persist
"""

from __future__ import annotations

from trips.plan_day_api import (
    execute_plan_next_day,
    plan_next_day,
    plan_next_day_sync,
    start_plan_next_day,
)

__all__ = [
    "plan_next_day",
    "plan_next_day_sync",
    "start_plan_next_day",
    "execute_plan_next_day",
]
