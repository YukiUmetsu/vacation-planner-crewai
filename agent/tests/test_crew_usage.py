"""Tests for crew kickoff token / latency helpers."""

from __future__ import annotations

from types import SimpleNamespace

from crew_kickoff import extract_token_usage
from vacation_planner_models import InvocationMeta


def test_extract_token_usage_from_dict_attr() -> None:
    result = SimpleNamespace(
        token_usage={
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "total_tokens": 140,
        }
    )
    assert extract_token_usage(result) == {
        "prompt_tokens": 100,
        "completion_tokens": 40,
        "total_tokens": 140,
    }


def test_extract_token_usage_sums_when_total_missing() -> None:
    result = SimpleNamespace(
        token_usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=None)
    )
    assert extract_token_usage(result)["total_tokens"] == 15


def test_extract_token_usage_empty_when_missing() -> None:
    assert extract_token_usage(SimpleNamespace()) == {}


def test_invocation_meta_accepts_usage_fields() -> None:
    meta = InvocationMeta(
        crew_name="day_plan",
        latency_ms=1200,
        prompt_tokens=800,
        completion_tokens=200,
        total_tokens=1000,
    )
    dumped = meta.model_dump(mode="json")
    assert dumped["latency_ms"] == 1200
    assert dumped["total_tokens"] == 1000
