"""CrewRunner factory defaults and failure modes."""

from __future__ import annotations

import pytest

from crews import runner as crew_runner


def test_crew_mode_defaults_to_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CREW_MODE", raising=False)
    assert crew_runner.crew_mode() == "fake"
    runner = crew_runner.get_crew_runner()
    assert runner.__class__.__name__ == "FakeCrewRunner"


def test_local_mode_fails_clearly_without_crewai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CREW_MODE", "local")

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # noqa: ANN001
        if name == "crewai" or name.startswith("crewai."):
            raise ImportError("simulated missing crewai")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="CREW_MODE=local requires CrewAI"):
        crew_runner.get_crew_runner()


def test_agentcore_mode_returns_agentcore_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CREW_MODE", "agentcore")
    runner = crew_runner.get_crew_runner()
    assert runner.__class__.__name__ == "AgentCoreRunner"


def test_request_override_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CREW_MODE", "fake")
    token = crew_runner.set_crew_mode_override("agentcore")
    try:
        assert crew_runner.crew_mode() == "agentcore"
        assert crew_runner.get_crew_runner().__class__.__name__ == "AgentCoreRunner"
        assert crew_runner.has_crew_mode_override() is True
    finally:
        crew_runner.reset_crew_mode_override(token)
    assert crew_runner.crew_mode() == "fake"
    assert crew_runner.has_crew_mode_override() is False


def test_async_plan_disabled_while_override_active(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.plan_day_worker import plan_next_day_async_enabled

    monkeypatch.setenv("CREW_MODE", "agentcore")
    monkeypatch.delenv("PLAN_NEXT_DAY_ASYNC", raising=False)
    assert plan_next_day_async_enabled() is True

    token = crew_runner.set_crew_mode_override("fake")
    try:
        # Dev UI override must stay sync so the worker cannot use a different mode.
        assert plan_next_day_async_enabled() is False
    finally:
        crew_runner.reset_crew_mode_override(token)
    assert plan_next_day_async_enabled() is True


def test_dev_header_override_only_when_auth_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    from auth import apply_dev_crew_mode_override, clear_dev_crew_mode_override

    monkeypatch.setenv("CREW_MODE", "fake")
    monkeypatch.setenv("AUTH_MODE", "cognito")
    token = apply_dev_crew_mode_override(
        {"headers": {"x-crew-mode": "agentcore"}}
    )
    try:
        assert crew_runner.crew_mode() == "fake"
    finally:
        clear_dev_crew_mode_override(token)

    monkeypatch.setenv("AUTH_MODE", "dev")
    token = apply_dev_crew_mode_override(
        {"headers": {"x-crew-mode": "agentcore"}}
    )
    try:
        assert crew_runner.crew_mode() == "agentcore"
    finally:
        clear_dev_crew_mode_override(token)
    assert crew_runner.crew_mode() == "fake"
