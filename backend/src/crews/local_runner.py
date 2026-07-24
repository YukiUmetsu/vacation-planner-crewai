"""In-process CrewAI runner for local development (CREW_MODE=local).

Delegates to agent ``crew_kickoff.run_crew`` so envelopes match AgentCore.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any


def _repo_agent_root() -> Path:
    env = os.getenv("AGENT_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[3] / "agent"


def _crews_root() -> Path:
    env = os.getenv("AGENT_CREWS_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return _repo_agent_root() / "crews"


def _ensure_import_paths(crew_dir: Path) -> None:
    """Crew dir (day_models/city_models) + shared models package on sys.path.

    Kept for tests and for any in-process import of crew adapter modules.
    """
    models_root = str((_repo_agent_root() / "models").resolve())
    if models_root not in sys.path:
        sys.path.insert(0, models_root)
    crew_str = str(crew_dir.resolve())
    if crew_str in sys.path:
        sys.path.remove(crew_str)
    sys.path.insert(0, crew_str)


@lru_cache(maxsize=1)
def _prepare_agent_imports() -> None:
    agent_root = _repo_agent_root()
    agent_str = str(agent_root.resolve())
    models_str = str((agent_root / "models").resolve())
    for path in (models_str, agent_str):
        if path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)
    env_path = agent_root / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=True)
    except ImportError:
        pass


class LocalCrewRunner:
    def _run(self, crew: str, inputs: dict[str, Any]) -> dict[str, Any]:
        _prepare_agent_imports()
        from crew_kickoff import run_crew

        return run_crew(crew, inputs)  # type: ignore[arg-type]

    def propose_cities(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return self._run("city_route", inputs)

    def plan_day(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return self._run("day_plan", inputs)

    def suggest_place(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return self._run("suggest_place", inputs)
