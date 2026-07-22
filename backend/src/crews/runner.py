"""CrewRunner protocol and factory."""

from __future__ import annotations

import os
from typing import Any, Protocol


class CrewRunner(Protocol):
    def propose_cities(self, inputs: dict[str, Any]) -> dict[str, Any]: ...

    def plan_day(self, inputs: dict[str, Any]) -> dict[str, Any]: ...


def crew_mode() -> str:
    # Default to fake so the backend venv works without CrewAI installed.
    # Use CREW_MODE=local only when agent crew deps are available; agentcore in AWS.
    return os.getenv("CREW_MODE", "fake").strip().lower() or "fake"


def get_crew_runner() -> CrewRunner:
    mode = crew_mode()
    if mode == "local":
        try:
            import crewai  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "CREW_MODE=local requires CrewAI in this environment. "
                "Use CREW_MODE=fake for backend-only work, or install/run against "
                "agent/crews dependencies. Production should use CREW_MODE=agentcore."
            ) from exc
        from crews.local_runner import LocalCrewRunner

        return LocalCrewRunner()
    if mode in {"fake", "mock"}:
        from crews.fake_runner import FakeCrewRunner

        return FakeCrewRunner()
    if mode == "agentcore":
        from crews.agentcore_runner import AgentCoreRunner
        return AgentCoreRunner()
    raise ValueError(f"Unknown CREW_MODE={mode!r}")
