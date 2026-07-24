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


def test_scorer_already_visited_accepts_comma_string() -> None:
    case = EvalCase(
        id="dedupe_csv",
        crew="day_plan",
        inputs={"already_visited": "sensoji, other"},
        expected={"min_places": 1},
        source_path=Path("dedupe_csv.json"),
    )
    result = run_case(
        case,
        {"places": [{"name": "Senso-ji", "place_key": "sensoji"}], "overnight_city": "Tokyo"},
    )
    assert result.passed is False
    assert any("already_visited" in msg for msg in result.failures)


def test_scorer_accepts_valid_suggest_place() -> None:
    case = EvalCase(
        id="suggest_ok",
        crew="suggest_place",
        inputs={
            "date": "2026-09-01",
            "remaining_minutes": 120,
            "already_visited": ["senso-ji|tokyo"],
            "energy_level": 3,
            "existing_places": [
                {"name": "A", "place_key": "a", "estimated_minutes": 60},
                {"name": "B", "place_key": "b", "estimated_minutes": 60},
                {"name": "C", "place_key": "c", "estimated_minutes": 60},
            ],
        },
        expected={"max_total_minutes": 510},
        source_path=Path("suggest_ok.json"),
    )
    result = run_case(
        case,
        {
            "name": "Yanaka",
            "place_key": "yanaka|tokyo",
            "estimated_minutes": 45,
            "travel_minutes_from_previous": 15,
            "operational_status": "open",
        },
    )
    assert result.passed is True


def test_scorer_rejects_suggest_place_over_remaining() -> None:
    case = EvalCase(
        id="suggest_heavy",
        crew="suggest_place",
        inputs={"remaining_minutes": 30, "date": "2026-09-01"},
        expected={},
        source_path=Path("suggest_heavy.json"),
    )
    result = run_case(
        case,
        {
            "name": "Long Museum",
            "place_key": "long|tokyo",
            "estimated_minutes": 90,
            "operational_status": "open",
        },
    )
    assert result.passed is False
    assert any("remaining_minutes" in msg for msg in result.failures)


def test_scorer_rejects_suggest_place_duplicate_existing() -> None:
    case = EvalCase(
        id="suggest_dupe",
        crew="suggest_place",
        inputs={
            "remaining_minutes": 120,
            "existing_places": [{"name": "A", "place_key": "a|tokyo", "estimated_minutes": 60}],
        },
        expected={},
        source_path=Path("suggest_dupe.json"),
    )
    result = run_case(
        case,
        {
            "name": "A again",
            "place_key": "a|tokyo",
            "estimated_minutes": 30,
            "operational_status": "open",
        },
    )
    assert result.passed is False
    assert any("existing day place_key" in msg for msg in result.failures)


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
                {"name": "Lunch Spot", "place_key": "lunch", "category": "food"},
                {"name": "Park", "place_key": "park", "category": "park"},
                {"name": "Dinner Spot", "place_key": "dinner", "category": "food"},
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


def test_scorer_rejects_energy_overload_and_closed_venues() -> None:
    case = EvalCase(
        id="quality",
        crew="day_plan",
        inputs={
            "overnight_city": "Tokyo",
            "energy_level": "1",
            "date": "2026-09-07",  # Monday
        },
        expected={"min_places": 1},
        source_path=Path("quality.json"),
    )
    result = run_case(
        case,
        {
            "overnight_city": "Tokyo",
            "places": [
                {
                    "name": "Closed Shop",
                    "place_key": "closed|tokyo",
                    "estimated_minutes": 60,
                    "operational_status": "closed",
                },
                {
                    "name": "Monday Closed Museum",
                    "place_key": "museum|tokyo",
                    "estimated_minutes": 200,
                    "operational_status": "open",
                    "closed_weekdays": [0],
                },
                {
                    "name": "Long Hike",
                    "place_key": "hike|tokyo",
                    "estimated_minutes": 300,
                    "travel_minutes_from_previous": 0,
                    "operational_status": "open",
                },
            ],
        },
    )
    assert result.passed is False
    assert any("permanently closed" in msg for msg in result.failures)
    assert any("closed on weekday 0" in msg for msg in result.failures)
    assert any("exceeds energy warning threshold 270" in msg for msg in result.failures)


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


def test_preference_fixtures_expose_graded_metrics() -> None:
    from evals.harness import aggregate_metrics, unwrap_eval_output
    from evals.scorers import collect_day_plan_metrics

    cases = {c.id: c for c in load_cases()}
    for case_id in (
        "day_plan_preference_food",
        "day_plan_preference_exclusion",
        "day_plan_preference_mismatch",
    ):
        assert case_id in cases, f"missing fixture {case_id}"

    fixtures = Path(__file__).resolve().parent / "fixtures"
    food = run_case(
        cases["day_plan_preference_food"],
        json.loads(
            (fixtures / "day_plan_preference_food.output.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    assert food.passed
    assert food.metrics["preference_relevance_score"] == 1.0
    assert food.metrics["grounding_rate"] == 1.0

    mismatch = run_case(
        cases["day_plan_preference_mismatch"],
        json.loads(
            (fixtures / "day_plan_preference_mismatch.output.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    assert mismatch.passed
    assert float(mismatch.metrics["preference_relevance_score"]) < 0.5

    exclusion = cases["day_plan_preference_exclusion"]
    domain = unwrap_eval_output(
        json.loads(
            (fixtures / "day_plan_preference_exclusion.output.json").read_text(
                encoding="utf-8"
            )
        )
    )
    metrics = collect_day_plan_metrics(domain, exclusion)
    assert metrics["explicit_exclusion_violation_rate"] == 0.0
    assert metrics["preference_relevance_score"] == 1.0

    violated = collect_day_plan_metrics(
        {
            **domain,
            "places": domain["places"]
            + [
                {
                    "name": "Club Example",
                    "place_key": "club|tokyo",
                    "category": "nightlife",
                    "estimated_minutes": 60,
                    "order_in_day": 5,
                }
            ],
        },
        exclusion,
    )
    assert violated["explicit_exclusion_violation_rate"] == 1.0

    csv_case = EvalCase(
        id="exclusion_csv",
        crew="day_plan",
        inputs={
            "overnight_city": "Tokyo",
            "excluded_categories": "nightlife, shopping",
        },
        expected={"min_places": 1},
        source_path=Path("exclusion_csv.json"),
    )
    csv_metrics = collect_day_plan_metrics(
        {
            "overnight_city": "Tokyo",
            "places": [
                {
                    "name": "Club Example",
                    "place_key": "club|tokyo",
                    "category": "nightlife",
                    "estimated_minutes": 60,
                    "order_in_day": 1,
                }
            ],
        },
        csv_case,
    )
    assert csv_metrics["explicit_exclusion_violation_rate"] == 1.0

    agg = aggregate_metrics([food, mismatch])
    assert "preference_relevance_score" in agg
    assert "schema_valid_rate" in agg


def test_load_cases_rejects_bad_crew(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"id": "x", "crew": "nope", "inputs": {}, "expected": {}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="crew must be"):
        load_cases(tmp_path)


def test_llm_preference_scorer_uses_injected_invoke() -> None:
    from evals.preference_scorer import LlmPreferenceScorer

    case = EvalCase(
        id="judge",
        crew="day_plan",
        inputs={"interests": "museum"},
        expected={"interests": ["museum"]},
        source_path=Path("judge.json"),
    )
    scorer = LlmPreferenceScorer(
        invoke=lambda _prompt: '{"preference_relevance_score": 0.25, "notes": "weak"}'
    )
    score = scorer.score_preference_relevance(
        {
            "places": [
                {
                    "name": "Mall",
                    "category": "other",
                    "place_key": "mall",
                    "estimated_minutes": 30,
                }
            ]
        },
        case,
    )
    assert score == 0.25


def test_llm_preference_scorer_falls_back_on_bad_json() -> None:
    from evals.preference_scorer import HeuristicPreferenceScorer, LlmPreferenceScorer

    case = EvalCase(
        id="judge_fallback",
        crew="day_plan",
        inputs={},
        expected={"interests": ["ramen"]},
        source_path=Path("judge_fallback.json"),
    )
    output = {
        "places": [
            {
                "name": "Ichiran",
                "category": "food",
                "reason_to_visit": "Lunch — ramen",
                "place_key": "ichiran",
                "estimated_minutes": 45,
            }
        ]
    }
    scorer = LlmPreferenceScorer(
        invoke=lambda _prompt: "not-json",
        fallback=HeuristicPreferenceScorer(),
    )
    assert scorer.score_preference_relevance(output, case) == 1.0


def test_metrics_report_writes_markdown(tmp_path: Path) -> None:
    from evals.report import build_metrics_report, write_metrics_report

    case = EvalCase(
        id="r1",
        crew="day_plan",
        inputs={"overnight_city": "Tokyo"},
        expected={"min_places": 1},
        source_path=Path("r1.json"),
    )
    result = run_case(
        case,
        {
            "overnight_city": "Tokyo",
            "places": [
                {
                    "name": "Park",
                    "place_key": "park",
                    "category": "park",
                    "estimated_minutes": 30,
                }
            ],
        },
    )
    report = build_metrics_report([result], preference_judge="heuristic")
    path = tmp_path / "metrics.md"
    write_metrics_report(report, path)
    text = path.read_text(encoding="utf-8")
    assert "Aggregate rates" in text
    assert "preference_relevance_score" in text or "schema_valid" in text


def test_cli_prints_aggregate_and_writes_report(tmp_path: Path) -> None:
    from evals.__main__ import main

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "one.json").write_text(
        json.dumps(
            {
                "id": "one",
                "crew": "day_plan",
                "inputs": {"overnight_city": "Tokyo"},
                "expected": {"min_places": 1},
            }
        ),
        encoding="utf-8",
    )
    (fixtures / "one.output.json").write_text(
        json.dumps(
            {
                "overnight_city": "Tokyo",
                "places": [
                    {
                        "name": "Park",
                        "place_key": "park",
                        "estimated_minutes": 20,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report = tmp_path / "out.json"
    assert main(["--fixtures-dir", str(fixtures), "--report", str(report)]) == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["summary"]["passed"] == 1
    assert "aggregates" in data
