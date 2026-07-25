"""Trip orchestration entrypoint (ADR 005): thin `TripService`.

Public API is unchanged; behavior lives in `trips.crud`, `trips.city_route`,
`trips.plan_day`, and `trips.day_edit`, each of which takes `table` /
`runner` / `safety` / `enqueue_plan_day` as explicit args and never imports
this module (see docs/architecture-decisions/005-services-domain-packages.md).
"""

from __future__ import annotations

from typing import Any, Callable

from crews.runner import CrewRunner, get_crew_runner
from db.protocols import DynamoDBTable
from models.api import ConfirmCitiesRequest
from safety.gate import SafetyGate, get_safety_gate

from trips import city_route, crud, day_edit, plan_day
from trips.city_route import (  # noqa: F401 — re-export surface for callers/tests
    assert_route_fits_window,
    overnight_city_for_day,
    synthetic_city_route,
)
from trips.crud import _validate  # noqa: F401 — used by confirm_cities below
from trips.day_edit import status_after_day_edit  # noqa: F401 — re-export surface
from trips.day_index import (  # noqa: F401 — re-export surface for callers/tests
    first_missing_day_index,
    resolve_plan_day_index,
)
from trips.prompts import (  # noqa: F401 — re-export surface for callers/tests
    _meal_guidance,
    rebuild_prior_days_summary,
    visited_keys_from_days,
)

# Kept for backwards compatibility — see city_route.py for the promoted name.
_assert_route_fits_window = assert_route_fits_window


class TripService:
    def __init__(
        self,
        *,
        table: DynamoDBTable | None = None,
        runner: CrewRunner | None = None,
        safety: SafetyGate | None = None,
        enqueue_plan_day: Callable[[str, str, int], None] | None = None,
    ) -> None:
        self._table = table
        self._runner = runner
        self._safety = safety
        self._enqueue_plan_day = enqueue_plan_day

    @property
    def runner(self) -> CrewRunner:
        if self._runner is None:
            self._runner = get_crew_runner()
        return self._runner

    @property
    def safety(self) -> SafetyGate:
        if self._safety is None:
            self._safety = get_safety_gate()
        return self._safety

    def _require_trip(self, user_sub: str, trip_id: str) -> dict[str, Any]:
        return crud._require_trip(user_sub=user_sub, trip_id=trip_id, table=self._table)

    def create_trip(self, user_sub: str, body: dict[str, Any]) -> dict[str, Any]:
        return crud.create_trip(user_sub=user_sub, body=body, table=self._table, safety=self.safety)

    def update_trip(self, user_sub: str, trip_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return crud.update_trip(
            user_sub=user_sub, trip_id=trip_id, body=body, table=self._table, safety=self.safety
        )

    def list_trips(self, user_sub: str) -> dict[str, Any]:
        return crud.list_trips(user_sub=user_sub, table=self._table)

    def delete_trip(self, user_sub: str, trip_id: str) -> dict[str, Any]:
        return crud.delete_trip(user_sub=user_sub, trip_id=trip_id, table=self._table)

    def get_trip(self, user_sub: str, trip_id: str) -> dict[str, Any]:
        return crud.get_trip(user_sub=user_sub, trip_id=trip_id, table=self._table)

    def propose_cities(self, user_sub: str, trip_id: str) -> dict[str, Any]:
        trip = self._require_trip(user_sub, trip_id)
        return city_route.propose_cities(
            user_sub=user_sub,
            trip_id=trip_id,
            trip=trip,
            table=self._table,
            runner=self.runner,
            safety=self.safety,
        )

    def confirm_cities(self, user_sub: str, trip_id: str, body: dict[str, Any]) -> dict[str, Any]:
        trip = self._require_trip(user_sub, trip_id)
        req = _validate(ConfirmCitiesRequest, body)
        return city_route.confirm_cities(
            user_sub=user_sub,
            trip_id=trip_id,
            trip=trip,
            req=req,
            table=self._table,
        )

    def plan_next_day(self, user_sub: str, trip_id: str) -> dict[str, Any]:
        """Plan the next day — sync 200 body, or async 202 body when agentcore."""
        return plan_day.plan_next_day(
            user_sub=user_sub,
            trip_id=trip_id,
            table=self._table,
            runner=self.runner,
            safety=self.safety,
            enqueue_plan_day=self._enqueue_plan_day,
        )

    def start_plan_next_day(self, user_sub: str, trip_id: str) -> dict[str, Any]:
        """Claim planning slot and enqueue worker; returns async response shape."""
        return plan_day.start_plan_next_day(
            user_sub=user_sub,
            trip_id=trip_id,
            table=self._table,
            runner=self.runner,
            safety=self.safety,
            enqueue_plan_day=self._enqueue_plan_day,
        )

    def execute_plan_next_day(
        self, user_sub: str, trip_id: str, day_index: int
    ) -> dict[str, Any]:
        """Worker path: run crew + enrich + persist for an already-claimed day."""
        return plan_day.execute_plan_next_day(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            table=self._table,
            runner=self.runner,
            safety=self.safety,
        )

    def suggest_place(
        self, user_sub: str, trip_id: str, day_index: int
    ) -> dict[str, Any]:
        """Research and append one place to an existing planned day."""
        return day_edit.suggest_place(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            table=self._table,
            runner=self.runner,
            safety=self.safety,
        )

    def remove_place(
        self, user_sub: str, trip_id: str, day_index: int, place_index: int
    ) -> dict[str, Any]:
        """Remove one place from a day by list index and reindex order_in_day."""
        return day_edit.remove_place(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            place_index=place_index,
            table=self._table,
        )

    def delete_day(
        self, user_sub: str, trip_id: str, day_index: int
    ) -> dict[str, Any]:
        """Delete an entire day plan and rewind planning cursors for gaps."""
        return day_edit.delete_day(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            table=self._table,
        )
