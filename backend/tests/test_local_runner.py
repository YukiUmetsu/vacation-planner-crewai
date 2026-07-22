"""LocalCrewRunner import paths (no CrewAI kickoff)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from crews.local_runner import _crews_root, _ensure_import_paths, _repo_agent_root


def test_unique_crew_model_modules_do_not_clash() -> None:
    crews = _crews_root()
    city_dir = crews / "city_route"
    day_dir = crews / "day_plan"
    if not (city_dir / "city_models.py").is_file() or not (day_dir / "day_models.py").is_file():
        pytest.skip("agent crew projects (city_models/day_models) not present")

    models_root = str((_repo_agent_root() / "models").resolve())
    path_before = list(sys.path)
    modules_before = {
        name: sys.modules.get(name) for name in ("city_models", "day_models")
    }

    try:
        if models_root not in sys.path:
            sys.path.insert(0, models_root)

        _ensure_import_paths(city_dir)
        import city_models

        _ensure_import_paths(day_dir)
        import day_models

        assert city_models.CityRoute.__name__ == "CityRoute"
        assert day_models.DayPlan.__name__ == "DayPlan"
        assert "city_models" in sys.modules
        assert "day_models" in sys.modules
        assert Path(sys.path[0]).resolve() == day_dir.resolve()
    finally:
        sys.path[:] = path_before
        for name, prior in modules_before.items():
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior
