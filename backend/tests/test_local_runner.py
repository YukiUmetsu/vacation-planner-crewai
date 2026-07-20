"""LocalCrewRunner path / models isolation (no CrewAI kickoff)."""

from __future__ import annotations

import sys
from pathlib import Path

from crews.local_runner import activate_crew_dir, load_crew_model_class, _crews_root


def test_load_crew_models_do_not_clash_across_crews() -> None:
    crews = _crews_root()
    city_dir = crews / "city_route"
    day_dir = crews / "day_plan"
    if not city_dir.is_dir() or not day_dir.is_dir():
        # Editable checkout layout assumed; skip if agent crews are absent.
        return

    activate_crew_dir(city_dir)
    city_route = load_crew_model_class(city_dir, "CityRoute")
    assert city_route.__name__ == "CityRoute"

    activate_crew_dir(day_dir)
    day_plan = load_crew_model_class(day_dir, "DayPlan")
    assert day_plan.__name__ == "DayPlan"

    # Unique module names — both remain importable afterward.
    assert "vacation_planner_crew_models_city_route" in sys.modules
    assert "vacation_planner_crew_models_day_plan" in sys.modules
    assert Path(sys.path[0]).resolve() == day_dir.resolve()
