"""Shared async gate for LLM-backed crew HTTP APIs."""

from __future__ import annotations

import os


def _explicit_async_flag(*env_names: str) -> bool | None:
    """Return True/False when an env forces async/sync; None means auto."""
    for env_name in env_names:
        raw = os.getenv(env_name)
        if raw is None:
            continue
        flag = raw.strip().lower()
        if flag in {"off", "0", "false", "no", "sync"}:
            return False
        if flag in {"on", "1", "true", "yes", "async"}:
            return True
        # auto / unknown → keep scanning or fall through
        if flag in {"auto", ""}:
            continue
    return None


def llm_async_enabled() -> bool:
    """Async for propose-cities / suggest-city / suggest-place.

    Default **on** (these must not block the HTTP path). Opt out with
    ``CREW_LLM_ASYNC=off`` (unit tests do this via conftest).
    """
    explicit = _explicit_async_flag("CREW_LLM_ASYNC")
    if explicit is not None:
        return explicit
    return True


def plan_day_async_enabled() -> bool:
    """Async for plan-next-day: ``PLAN_NEXT_DAY_ASYNC`` → auto agentcore.

    ``CREW_LLM_ASYNC=on`` also forces plan-day async. ``CREW_LLM_ASYNC=off`` does
    **not** force plan-day sync (tests use that only for propose/suggest).
    """
    explicit = _explicit_async_flag("PLAN_NEXT_DAY_ASYNC")
    if explicit is not None:
        return explicit
    raw = os.getenv("CREW_LLM_ASYNC")
    if raw is not None and raw.strip().lower() in {"on", "1", "true", "yes", "async"}:
        return True
    from crews.runner import crew_mode

    return crew_mode() == "agentcore"
