"""CrewRunner protocol and factory."""

from __future__ import annotations

import os
from contextvars import ContextVar, Token
from typing import Any, Protocol

# Request-scoped override (AUTH_MODE=dev + X-Crew-Mode only). Never set in Lambda cognito.
_crew_mode_override: ContextVar[str | None] = ContextVar(
    "crew_mode_override", default=None
)

# Modes the local UI may request. ``local`` allowed for smoke; UI uses fake | agentcore.
DEV_CREW_MODE_OVERRIDE_VALUES = frozenset({"fake", "mock", "local", "agentcore"})


class CrewRunner(Protocol):
    def propose_cities(self, inputs: dict[str, Any]) -> dict[str, Any]: ...

    def plan_day(self, inputs: dict[str, Any]) -> dict[str, Any]: ...

    def suggest_place(self, inputs: dict[str, Any]) -> dict[str, Any]: ...


def set_crew_mode_override(mode: str | None) -> Token[str | None]:
    """Set request-scoped CREW_MODE override; returns a reset token."""
    return _crew_mode_override.set(mode)


def reset_crew_mode_override(token: Token[str | None]) -> None:
    _crew_mode_override.reset(token)


def has_crew_mode_override() -> bool:
    """True when a request-scoped override is active (dev X-Crew-Mode)."""
    return _crew_mode_override.get() is not None


def crew_mode() -> str:
    # Default to fake so the backend venv works without CrewAI installed.
    # Use CREW_MODE=local only when agent crew deps are available; agentcore in AWS.
    override = _crew_mode_override.get()
    if override:
        return override
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
