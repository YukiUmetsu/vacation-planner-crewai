from pathlib import Path
from typing import Any

from evals.case import load_cases
from evals.compare_orchestration import ORCHESTRATION_SMOKE_IDS, decide_keep_three_agent
from evals.cost import estimate_cost_usd
from crew_kickoff import _model_class, extract_token_usage


def test_orchestration_smoke_ids_exist() -> None:
    ids = {c.id for c in load_cases()}
    missing = [i for i in ORCHESTRATION_SMOKE_IDS if i not in ids]
    assert not missing, f"missing smoke fixtures: {missing}"


def test_estimate_cost_usd_from_tokens() -> None:
    cost = estimate_cost_usd({"prompt_tokens": 1000, "completion_tokens": 1000})
    assert cost is not None
    assert cost > 0


def test_model_class_day_plan_single() -> None:
    from vacation_planner_models import CityRoute, DayPlanWithQuality, Place

    assert _model_class("day_plan") is DayPlanWithQuality
    assert _model_class("day_plan_single") is DayPlanWithQuality
    assert _model_class("suggest_place") is Place
    assert _model_class("city_route") is CityRoute


def test_extract_token_usage_skips_empty_shell() -> None:
    class EmptyUsage:
        prompt_tokens = None
        completion_tokens = None
        total_tokens = None

    class GoodUsage:
        prompt_tokens = 10
        completion_tokens = 5
        total_tokens = 15

    class Result:
        token_usage = EmptyUsage()
        usage_metrics = GoodUsage()

    assert extract_token_usage(Result()) == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }


def test_decide_keep_three_agent_quality_and_budget() -> None:
    multi = {
        "hard_constraint_pass_rate": 0.9,
        "food_only_day_rate": 0.05,
        "duplicate_rate": 0.0,
        "closed_place_case_rate": 0.05,
        "preference_relevance_score": 0.7,
        "latency_ms": 60_000,
        "cost_usd": 0.02,
    }
    single = {
        "hard_constraint_pass_rate": 0.7,
        "food_only_day_rate": 0.2,
        "duplicate_rate": 0.1,
        "closed_place_case_rate": 0.1,
        "preference_relevance_score": 0.5,
        "latency_ms": 30_000,
        "cost_usd": 0.01,
    }
    keep, reasons = decide_keep_three_agent(multi, single)
    assert keep is True
    assert reasons


def test_decide_refuse_when_cost_missing() -> None:
    multi = {
        "hard_constraint_pass_rate": 0.9,
        "food_only_day_rate": 0.0,
        "duplicate_rate": 0.0,
        "closed_place_case_rate": 0.0,
        "preference_relevance_score": 0.8,
        "latency_ms": 40_000,
    }
    single = {
        "hard_constraint_pass_rate": 0.7,
        "food_only_day_rate": 0.2,
        "duplicate_rate": 0.1,
        "closed_place_case_rate": 0.1,
        "preference_relevance_score": 0.5,
        "latency_ms": 20_000,
    }
    keep, reasons = decide_keep_three_agent(multi, single)
    assert keep is False
    assert any("cost unavailable" in r for r in reasons)


def test_decide_prefer_single_when_within_margin() -> None:
    multi = {
        "hard_constraint_pass_rate": 0.8,
        "food_only_day_rate": 0.1,
        "duplicate_rate": 0.05,
        "closed_place_case_rate": 0.05,
        "preference_relevance_score": 0.55,
        "latency_ms": 90_000,
        "cost_usd": 0.05,
    }
    single = {
        "hard_constraint_pass_rate": 0.78,
        "food_only_day_rate": 0.11,
        "duplicate_rate": 0.05,
        "closed_place_case_rate": 0.05,
        "preference_relevance_score": 0.54,
        "latency_ms": 30_000,
        "cost_usd": 0.01,
    }
    keep, reasons = decide_keep_three_agent(multi, single)
    assert keep is False
    assert any("prefer single-call" in r for r in reasons)


def test_orchestration_compare_parallel_arms(tmp_path: Path) -> None:
    import threading
    import time as time_mod

    from evals.case import EvalCase
    from evals.compare_orchestration import run_orchestration_compare

    lock = threading.Lock()
    active = 0
    max_active = 0

    def producer(case: EvalCase) -> dict[str, Any]:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time_mod.sleep(0.05)
        with lock:
            active -= 1
        return {
            "result": {
                "day_index": 1,
                "date": "2026-09-01",
                "overnight_city": "Tokyo",
                "theme": "t",
                "summary": "s",
                "places": [
                    {
                        "name": "Lunch Spot",
                        "category": "food",
                        "reason_to_visit": "Lunch — test",
                        "estimated_minutes": 60,
                        "order_in_day": 1,
                        "place_key": "lunch",
                    },
                    {
                        "name": "Park",
                        "category": "park",
                        "reason_to_visit": "walk",
                        "estimated_minutes": 45,
                        "order_in_day": 2,
                        "place_key": "park",
                    },
                    {
                        "name": "Dinner Spot",
                        "category": "food",
                        "reason_to_visit": "Dinner — test",
                        "estimated_minutes": 60,
                        "order_in_day": 3,
                        "place_key": "dinner",
                    },
                ],
            },
            "quality": {
                "passes_relevance": True,
                "relevance_score": 4,
                "constraint_score": 4,
                "failure_tags": [],
                "notes": "",
            },
            "invocation": {
                "latency_ms": 50,
                "prompt_tokens": 10,
                "completion_tokens": 5,
            },
        }

    case = EvalCase(
        id="day_plan_parallel_probe",
        crew="day_plan",
        inputs={
            "overnight_city": "Tokyo",
            "day_index": "1",
            "date": "2026-09-01",
            "preferences": "food",
        },
        expected={"min_places": 3},
        source_path=tmp_path / "day_plan_parallel_probe.json",
    )
    report = run_orchestration_compare(
        cases=[case],
        producer=producer,
        runs_dir=tmp_path / "runs",
        parallel_arms=True,
    )
    assert report["parallel_arms"] is True
    assert report["arms"]["day_plan"]["passed"] + report["arms"]["day_plan"]["failed"] == 1
    assert (
        report["arms"]["day_plan_single"]["passed"]
        + report["arms"]["day_plan_single"]["failed"]
        == 1
    )
    assert max_active >= 2


def test_format_orchestration_summary_table() -> None:
    from evals.compare_orchestration import format_orchestration_summary

    report = {
        "case_count": 8,
        "decision": {
            "keep_three_agent": True,
            "reasons": ["hard_constraint_pass_rate +25.0 pp (≥ 10.0)"],
        },
        "arms": {
            "day_plan": {
                "passed": 8,
                "failed": 0,
                "aggregates": {
                    "hard_constraint_pass_rate": 1.0,
                    "schema_valid_rate": 1.0,
                    "preference_relevance_score": 0.875,
                    "latency_ms": 36000,
                    "cost_usd": 0.027,
                },
            },
            "day_plan_single": {
                "passed": 6,
                "failed": 2,
                "aggregates": {
                    "hard_constraint_pass_rate": 0.75,
                    "schema_valid_rate": 0.75,
                    "preference_relevance_score": 0.93,
                    "latency_ms": 26000,
                    "cost_usd": 0.025,
                },
            },
        },
    }
    text = format_orchestration_summary(report)
    assert "keep 3-agent = **True**" in text
    assert "| Hard-constraint pass |" in text
    assert "**+25 pp**" in text


def test_format_orchestration_markdown_includes_progress() -> None:
    from evals.compare_orchestration import format_orchestration_markdown

    report = {
        "run_id": "test-run",
        "case_count": 2,
        "parallel_arms": True,
        "progress": [
            "Orchestration compare run_id=test-run cases=2",
            "[1/2] case_a …",
            "  day_plan: PASS (1.0s)",
            "  day_plan_single: FAIL (1.0s)",
            "[2/2] case_b …",
        ],
        "decision": {
            "keep_three_agent": True,
            "reasons": ["hard_constraint_pass_rate +25.0 pp (≥ 10.0)"],
        },
        "arms": {
            "day_plan": {
                "passed": 2,
                "failed": 0,
                "aggregates": {"hard_constraint_pass_rate": 1.0},
                "sample_failures": [],
            },
            "day_plan_single": {
                "passed": 1,
                "failed": 1,
                "aggregates": {"hard_constraint_pass_rate": 0.75},
                "sample_failures": ["case_a: boom"],
            },
        },
    }
    text = format_orchestration_markdown(report)
    assert "## Summary" in text
    assert "## Progress" in text
    assert "[1/2] case_a …" in text
    assert "[2/2] case_b …" in text
    assert "| Hard-constraint pass |" in text


def test_live_report_rewritten_during_compare(tmp_path: Path) -> None:
    from evals.case import EvalCase
    from evals.compare_orchestration import run_orchestration_compare

    report_path = tmp_path / "live.md"

    def producer(case: EvalCase) -> dict[str, Any]:
        return {
            "result": {
                "day_index": 1,
                "date": "2026-09-01",
                "overnight_city": "Tokyo",
                "theme": "t",
                "summary": "s",
                "places": [
                    {
                        "name": "Lunch Spot",
                        "category": "food",
                        "reason_to_visit": "Lunch — test",
                        "estimated_minutes": 60,
                        "order_in_day": 1,
                        "place_key": "lunch",
                    },
                    {
                        "name": "Park",
                        "category": "park",
                        "reason_to_visit": "walk",
                        "estimated_minutes": 45,
                        "order_in_day": 2,
                        "place_key": "park",
                    },
                    {
                        "name": "Dinner Spot",
                        "category": "food",
                        "reason_to_visit": "Dinner — test",
                        "estimated_minutes": 60,
                        "order_in_day": 3,
                        "place_key": "dinner",
                    },
                ],
            },
            "quality": {
                "passes_relevance": True,
                "relevance_score": 4,
                "constraint_score": 4,
                "failure_tags": [],
                "notes": "",
            },
            "invocation": {
                "latency_ms": 50,
                "prompt_tokens": 10,
                "completion_tokens": 5,
            },
        }

    case = EvalCase(
        id="day_plan_live_report_probe",
        crew="day_plan",
        inputs={
            "overnight_city": "Tokyo",
            "day_index": "1",
            "date": "2026-09-01",
            "preferences": "food",
        },
        expected={"min_places": 3},
        source_path=tmp_path / "day_plan_live_report_probe.json",
    )
    report = run_orchestration_compare(
        cases=[case],
        producer=producer,
        runs_dir=tmp_path / "runs",
        parallel_arms=False,
        report_path=report_path,
    )
    assert report_path.is_file()
    final = report_path.read_text(encoding="utf-8")
    assert "## Summary" in final
    assert "## Progress" in final
    assert "[1/1]" in final
    assert report.get("progress")
    progress_log = (tmp_path / "runs" / report["run_id"] / "progress.log").read_text(
        encoding="utf-8"
    )
    assert "[1/1]" in progress_log
