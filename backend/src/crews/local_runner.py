"""In-process CrewAI runner for local development (CREW_MODE=local)."""

from __future__ import annotations

import importlib.util
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


def _is_crew_project_path(path: str, crews_root: Path) -> bool:
    try:
        resolved = Path(path).resolve()
        return crews_root.resolve() in resolved.parents or resolved == crews_root.resolve()
    except OSError:
        return False


def activate_crew_dir(crew_dir: Path) -> None:
    """Put ``crew_dir`` first on ``sys.path`` and drop a stale ``models`` module.

    Both crew projects expose ``models.py``. Caching the first import as
    ``sys.modules['models']`` breaks the second crew in the same process.
    """
    crew_dir = crew_dir.resolve()
    crews_root = _crews_root().resolve()
    sys.path[:] = [
        p
        for p in sys.path
        if not _is_crew_project_path(p, crews_root) or Path(p).resolve() == crew_dir
    ]
    crew_str = str(crew_dir)
    if crew_str in sys.path:
        sys.path.remove(crew_str)
    sys.path.insert(0, crew_str)
    sys.modules.pop("models", None)


def load_crew_model_class(crew_dir: Path, class_name: str) -> type:
    """Load a Pydantic model from a crew's ``models.py`` without polluting ``models``."""
    models_root = _repo_agent_root() / "models"
    models_root_str = str(models_root.resolve())
    if models_root_str not in sys.path:
        sys.path.insert(0, models_root_str)

    models_path = crew_dir.resolve() / "models.py"
    module_name = f"vacation_planner_crew_models_{crew_dir.name}"
    spec = importlib.util.spec_from_file_location(module_name, models_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load models from {models_path}")
    module = importlib.util.module_from_spec(spec)
    # Register under a unique name so city_route and day_plan do not clash.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return getattr(module, class_name)


def _kickoff(crew_dir: Path, inputs: dict[str, Any], model_name: str) -> dict[str, Any]:
    _load_dotenv_once()
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    (crew_dir / "logs").mkdir(exist_ok=True)

    activate_crew_dir(crew_dir)
    model_cls = load_crew_model_class(crew_dir, model_name)

    from crewai.project import load_crew

    crew, default_inputs = load_crew(crew_dir / "crew.jsonc")
    _disable_llm_stream(crew)
    result = crew.kickoff(inputs={**default_inputs, **inputs})
    return extract_pydantic_dict(result, model_cls)


class LocalCrewRunner:
    def propose_cities(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return _kickoff(_crews_root() / "city_route", inputs, "CityRoute")

    def plan_day(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return _kickoff(_crews_root() / "day_plan", inputs, "DayPlan")
