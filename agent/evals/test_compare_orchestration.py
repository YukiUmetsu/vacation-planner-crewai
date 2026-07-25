from evals.compare_orchestration import decide_keep_three_agent
from evals.cost import estimate_cost_usd
from crew_kickoff import _model_class, extract_token_usage


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
