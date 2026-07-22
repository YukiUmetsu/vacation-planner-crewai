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
