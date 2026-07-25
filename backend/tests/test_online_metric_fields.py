"""Online metric field coercion."""

from __future__ import annotations

from ops.worker_observability import _as_metric_int, _invocation_metric_fields


def test_as_metric_int_coerces_strings() -> None:
    assert _as_metric_int("1200") == 1200
    assert _as_metric_int(1200.0) == 1200
    assert _as_metric_int("-1") is None
    assert _as_metric_int(None) is None


def test_invocation_metric_fields_includes_latency_and_tokens() -> None:
    fields = _invocation_metric_fields(
        {
            "crew_name": "day_plan",
            "latency_ms": "4500",
            "prompt_tokens": 100,
            "completion_tokens": "50",
            "total_tokens": 150,
        }
    )
    assert fields["latency_ms"] == 4500
    assert fields["prompt_tokens"] == 100
    assert fields["completion_tokens"] == 50
    assert fields["total_tokens"] == 150
