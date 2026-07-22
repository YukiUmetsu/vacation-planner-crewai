"""In-process CrewAI runner for local development (CREW_MODE=local)."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from crews.extract import extract_pydantic_dict


def _repo_agent_root() -> Path:
    env = os.getenv("AGENT_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    # backend/src/crews/local_runner.py -> backend -> vacation_planner -> agent
    return Path(__file__).resolve().parents[3] / "agent"


def _crews_root() -> Path:
    env = os.getenv("AGENT_CREWS_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return _repo_agent_root() / "crews"


@lru_cache(maxsize=1)
def _load_dotenv_once() -> None:
    agent_root = _repo_agent_root()
    env_path = agent_root / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=True)
    except ImportError:
        if env_path.is_file():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _disable_llm_stream(crew: Any) -> None:
    for agent in crew.agents:
        llm = getattr(agent, "llm", None)
        if llm is not None and hasattr(llm, "stream"):
            llm.stream = False


def _ensure_import_paths(crew_dir: Path) -> None:
    """Crew dir (day_models/city_models) + shared models package on sys.path."""
    models_root = str((_repo_agent_root() / "models").resolve())
    if models_root not in sys.path:
        sys.path.insert(0, models_root)
    crew_str = str(crew_dir.resolve())
    if crew_str in sys.path:
        sys.path.remove(crew_str)
    sys.path.insert(0, crew_str)


def _kickoff(crew_dir: Path, inputs: dict[str, Any], model_cls: type) -> dict[str, Any]:
    _load_dotenv_once()
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    (crew_dir / "logs").mkdir(exist_ok=True)

    _ensure_import_paths(crew_dir)

    from crewai.project import load_crew

    crew, default_inputs = load_crew(crew_dir / "crew.jsonc")
    _disable_llm_stream(crew)
    result = crew.kickoff(inputs={**default_inputs, **inputs})
    return extract_pydantic_dict(result, model_cls)


class LocalCrewRunner:
    def propose_cities(self, inputs: dict[str, Any]) -> dict[str, Any]:
        from vacation_planner_models import CityRoute

        return _kickoff(_crews_root() / "city_route", inputs, CityRoute)

    def plan_day(self, inputs: dict[str, Any]) -> dict[str, Any]:
        from vacation_planner_models import DayPlan

        return _kickoff(_crews_root() / "day_plan", inputs, DayPlan)

    def suggest_place(self, inputs: dict[str, Any]) -> dict[str, Any]:
        from vacation_planner_models import Place

        return _kickoff(_crews_root() / "suggest_place", inputs, Place)
