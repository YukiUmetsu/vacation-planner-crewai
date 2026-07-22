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


def test_run_case_with_empty_expected_skips_bounds_checks() -> None:
    case = EvalCase(
        id="manual",
        crew="day_plan",
        inputs={"overnight_city": "Tokyo"},
        expected={},
        source_path=Path("manual.json"),
    )
    result = run_case(case, {"places": [], "overnight_city": "Tokyo"})
    assert result.passed is True


def test_scorer_rejects_too_few_places() -> None:
    case = EvalCase(
        id="needs_more_places",
        crew="day_plan",
        inputs={},
        expected={"min_places": 3},
        source_path=Path("needs_more_places.json"),
    )
    result = run_case(case, {"places": [{"name": "A", "place_key": "a"}]})
    assert result.passed is False
    assert any("at least 3 places" in msg for msg in result.failures)


def test_scorer_rejects_already_visited_overlap() -> None:
    case = EvalCase(
        id="dedupe",
        crew="day_plan",
        inputs={"already_visited": ["sensoji"]},
        expected={"min_places": 1},
        source_path=Path("dedupe.json"),
    )
    result = run_case(
        case,
        {"places": [{"name": "Senso-ji", "place_key": "sensoji"}], "overnight_city": "Tokyo"},
    )
    assert result.passed is False
    assert any("already_visited" in msg for msg in result.failures)


def test_scorer_accepts_valid_day_plan() -> None:
    case = EvalCase(
        id="ok_day",
        crew="day_plan",
        inputs={"overnight_city": "Tokyo", "already_visited": ["old"]},
        expected={"min_places": 3, "max_places": 6, "forbidden_place_keys": ["banned"]},
        source_path=Path("ok_day.json"),
    )
    result = run_case(
        case,
        {
            "overnight_city": "Tokyo",
            "places": [
                {"name": "A", "place_key": "a"},
                {"name": "B", "place_key": "b"},
                {"name": "C", "place_key": "c"},
            ],
        },
    )
    assert result.passed is True
    assert result.failures == ()


def test_scorer_rejects_city_route_nights_mismatch() -> None:
    case = EvalCase(
        id="bad_nights",
        crew="city_route",
        inputs={},
        expected={"min_cities": 1},
        source_path=Path("bad_nights.json"),
    )
    result = run_case(
        case,
        {
            "cities": [{"city": "Tokyo", "nights": 2}],
            "total_nights": 5,
        },
    )
    assert result.passed is False
    assert any("total_nights" in msg for msg in result.failures)


def test_scorer_rejects_malformed_nights_without_raising() -> None:
    case = EvalCase(
        id="bad_nights_str",
        crew="city_route",
        inputs={},
        expected={},
        source_path=Path("bad_nights_str.json"),
    )
    result = run_case(
        case,
        {
            "cities": [{"city": "Tokyo", "nights": "two"}],
            "total_nights": "five",
        },
    )
    assert result.passed is False
    assert any("cities[0].nights" in msg for msg in result.failures)
    assert any("total_nights" in msg for msg in result.failures)


def test_example_offline_output_passes_scorer() -> None:
    cases = load_cases()
    example = next(c for c in cases if c.id == "day_plan_example_shape")
    output_path = example.source_path.with_suffix(".output.json")
    assert output_path.is_file(), "expected day_plan_example_shape.output.json golden"
    output = json.loads(output_path.read_text(encoding="utf-8"))
    result = run_case(example, output)
    assert result.passed is True, result.failures


def test_offline_cli_skips_missing_outputs_and_passes_golden(tmp_path: Path) -> None:
    from evals.__main__ import main

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "with_output.json").write_text(
        json.dumps(
            {
                "id": "with_output",
                "crew": "day_plan",
                "inputs": {"overnight_city": "Tokyo"},
                "expected": {"min_places": 1},
            }
        ),
        encoding="utf-8",
    )
    (fixtures / "with_output.output.json").write_text(
        json.dumps(
            {
                "overnight_city": "Tokyo",
                "places": [{"name": "A", "place_key": "a"}],
            }
        ),
        encoding="utf-8",
    )
    (fixtures / "no_output.json").write_text(
        json.dumps(
            {
                "id": "no_output",
                "crew": "day_plan",
                "inputs": {"overnight_city": "Tokyo"},
                "expected": {"min_places": 3},
            }
        ),
        encoding="utf-8",
    )
    assert main(["--fixtures-dir", str(fixtures)]) == 0



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
