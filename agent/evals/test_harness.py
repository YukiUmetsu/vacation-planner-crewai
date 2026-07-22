"""Harness smoke tests (no Bedrock, no CrewAI kickoff)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.case import EvalCase, load_cases
from evals.harness import run_case, run_cases


def test_load_example_fixture() -> None:
    cases = load_cases()
    assert any(c.id == "day_plan_example_shape" for c in cases)
    example = next(c for c in cases if c.id == "day_plan_example_shape")
    assert example.crew == "day_plan"
    assert "overnight_city" in example.inputs


def test_run_case_with_empty_expected_passes_until_scorers_exist() -> None:
    case = EvalCase(
        id="manual",
        crew="day_plan",
        inputs={"overnight_city": "Tokyo"},
        expected={},
        source_path=Path("manual.json"),
    )
    result = run_case(case, {"places": []})
    assert result.passed is True


def test_stub_scorer_fails_closed_when_expected_is_set() -> None:
    case = EvalCase(
        id="needs_scorer",
        crew="day_plan",
        inputs={},
        expected={"min_places": 3},
        source_path=Path("needs_scorer.json"),
    )
    result = run_case(case, {"places": [{"name": "A"}]})
    assert result.passed is False
    assert any("LEARNING" in msg for msg in result.failures)


def test_run_cases_records_producer_errors() -> None:
    case = EvalCase(
        id="boom",
        crew="city_route",
        inputs={},
        expected={},
        source_path=Path("boom.json"),
    )

    def producer(_case: EvalCase) -> dict:
        raise RuntimeError("no aws")

    results = run_cases([case], producer)
    assert len(results) == 1
    assert results[0].passed is False
    assert "RuntimeError" in results[0].failures[0]


def test_fixture_files_are_valid_json() -> None:
    root = Path(__file__).resolve().parent / "fixtures"
    files = list(root.glob("*.json"))
    assert files, "expected at least one example fixture"
    for path in files:
        if path.name.startswith("_"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)


def test_load_cases_rejects_bad_crew(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"id": "x", "crew": "nope", "inputs": {}, "expected": {}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="crew must be"):
        load_cases(tmp_path)
