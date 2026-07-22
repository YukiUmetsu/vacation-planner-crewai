"""Eval case schema and fixture loading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

CrewName = Literal["day_plan", "city_route", "suggest_place"]


@dataclass(frozen=True)
class EvalCase:
    """One offline evaluation case loaded from JSON under ``fixtures/``."""

    id: str
    crew: CrewName
    inputs: dict[str, Any]
    """Crew kickoff inputs (same shape as ``invoke_payload`` / ``run_crew``)."""

    expected: dict[str, Any]
    """Hints for scorers (e.g. ``min_places``, ``forbidden_place_keys``)."""

    source_path: Path


def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


def load_cases(directory: Path | None = None) -> list[EvalCase]:
    """Load ``*.json`` fixtures. Skips files starting with ``_``."""
    root = directory or fixtures_dir()
    if not root.is_dir():
        return []

    cases: list[EvalCase] = []
    for path in sorted(root.glob("*.json")):
        if path.name.startswith("_") or path.name.endswith(".output.json"):
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: fixture root must be a JSON object")
        case_id = str(raw.get("id") or path.stem)
        crew = raw.get("crew")
        if crew not in ("day_plan", "city_route", "suggest_place"):
            raise ValueError(f"{path}: crew must be day_plan, city_route, or suggest_place")
        inputs = raw.get("inputs")
        if not isinstance(inputs, dict):
            raise ValueError(f"{path}: inputs must be an object")
        expected = raw.get("expected") or {}
        if not isinstance(expected, dict):
            raise ValueError(f"{path}: expected must be an object")
        cases.append(
            EvalCase(
                id=case_id,
                crew=crew,
                inputs=inputs,
                expected=expected,
                source_path=path,
            )
        )
    return cases
