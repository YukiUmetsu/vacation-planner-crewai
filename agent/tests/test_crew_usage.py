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


def test_quiet_tracing_suppresses_trace_batch_panel(monkeypatch) -> None:
    import os

    from rich.console import Console
    from rich.panel import Panel

    import crew_kickoff as ck

    monkeypatch.setenv("EVALS_QUIET", "1")
    monkeypatch.setattr(ck, "_QUIET_TRACING_INSTALLED", False)
    if getattr(Console, "_vacation_planner_quiet_print", False):
        monkeypatch.setattr(Console, "_vacation_planner_quiet_print", False, raising=False)

    ck.install_quiet_crewai_tracing()
    from crewai.events.listeners.tracing.utils import (
        set_suppress_tracing_messages,
        should_enable_tracing,
    )

    set_suppress_tracing_messages(True)
    assert should_enable_tracing(override=None) is False
    assert should_enable_tracing(override=False) is False
    assert os.environ.get("CREWAI_TRACING_ENABLED") == "false"

    console = Console(record=True, width=80)
    console.print(Panel("hidden", title="Trace Batch Finalization"))
    console.print(Panel("hello", title="Normal Panel"))
    text = console.export_text()
    assert "Trace Batch Finalization" not in text
    assert "hello" in text


def test_is_bedrock_tooluse_error_detects_wrapped_model_error() -> None:
    from crew_kickoff import _is_bedrock_tooluse_error

    root = RuntimeError(
        "Model error: Model produced invalid sequence as part of ToolUse. "
        "Please refer to the model tool use troubleshooting guide."
    )
    wrapped = RuntimeError("ConverterError: failed")
    wrapped.__cause__ = root
    assert _is_bedrock_tooluse_error(wrapped) is True
    assert _is_bedrock_tooluse_error(root) is True
    assert _is_bedrock_tooluse_error(ValueError("schema invalid")) is False


def test_tooluse_retry_attempts_from_env(monkeypatch) -> None:
    from crew_kickoff import _tooluse_retry_attempts

    monkeypatch.setenv("CREW_TOOLUSE_RETRIES", "2")
    assert _tooluse_retry_attempts() == 3
    monkeypatch.setenv("CREW_TOOLUSE_RETRIES", "0")
    assert _tooluse_retry_attempts() == 1
