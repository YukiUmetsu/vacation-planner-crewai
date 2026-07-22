"""Safety gate stub — Bedrock Guardrails replace KeywordSafetyGate later."""

from __future__ import annotations

import os
from typing import Protocol

from http_utils import ApiError


class SafetyGate(Protocol):
    def check_text(self, text: str, *, source: str) -> None: ...


class SafetyRejected(ApiError):
    def __init__(self, source: str, detail: str = "content rejected by safety gate") -> None:
        super().__init__(400, detail, code="safety_rejected")
        self.source = source


class NoopSafetyGate:
    def check_text(self, text: str, *, source: str) -> None:
        return None


_DEFAULT_DENY = (
    "ignore previous instructions",
    "ignore all previous",
    "disregard your system prompt",
)


class KeywordSafetyGate:
    def __init__(self, deny_phrases: tuple[str, ...] | None = None) -> None:
        self._deny = tuple(p.lower() for p in (deny_phrases or _DEFAULT_DENY))

    def check_text(self, text: str, *, source: str) -> None:
        lowered = (text or "").lower()
        for phrase in self._deny:
            if phrase in lowered:
                raise SafetyRejected(source, f"blocked phrase in {source}")


def safety_mode() -> str:
    return os.getenv("SAFETY_MODE", "keyword").strip().lower() or "keyword"


def get_safety_gate() -> SafetyGate:
    mode = safety_mode()
    if mode in {"off", "noop", "none"}:
        return NoopSafetyGate()
    if mode in {"bedrock", "guardrails"}:
        from services.bedrock_safety import BedrockGuardrailsSafetyGate

        return BedrockGuardrailsSafetyGate.from_env()
    if mode in {"keyword", "keywords"}:
        return KeywordSafetyGate()
    raise ApiError(
        500,
        f"Unknown SAFETY_MODE={mode!r} (expected keyword|bedrock|off)",
        code="safety_misconfigured",
    )
