"""Safety gates — keyword denylist or Bedrock ApplyGuardrail."""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from typing import Literal, Protocol

from http_utils import ApiError
from safety.metrics import log_safety_metric

Direction = Literal["input", "output"]

_DEFAULT_DENY = (
    "ignore previous instructions",
    "ignore all previous",
    "disregard your system prompt",
    "ignore your instructions",
    "ignore all instructions",
    "disregard previous instructions",
    "forget previous instructions",
    "override your system",
    "new system prompt",
    "reveal your system prompt",
    "developer mode",
    "jailbreak mode",
    "do anything now",
)


class SafetyGate(Protocol):
    def check_text(
        self,
        text: str,
        *,
        source: str,
        direction: Direction = "input",
        trip_id: str | None = None,
    ) -> None: ...

    def check_texts(
        self,
        fields: Mapping[str, str | None],
        *,
        direction: Direction = "input",
        trip_id: str | None = None,
    ) -> None: ...


class SafetyRejected(ApiError):
    def __init__(self, source: str, detail: str = "content rejected by safety gate") -> None:
        super().__init__(400, detail, code="safety_rejected")
        self.source = source


class SafetyCheckUnavailable(ApiError):
    """Raised when INPUT Guardrail cannot be evaluated (fail-closed before GenAI)."""

    def __init__(self, detail: str = "safety check unavailable") -> None:
        super().__init__(503, detail, code="safety_check_unavailable", retryable=True)


def safety_mode() -> str:
    return os.getenv("SAFETY_MODE", "keyword").strip().lower() or "keyword"


def safety_output_mode() -> str:
    """observe (default): log OUTPUT interventions but persist. enforce: reject."""
    raw = os.getenv("SAFETY_OUTPUT_MODE", "observe").strip().lower() or "observe"
    if raw in {"enforce", "block", "reject"}:
        return "enforce"
    return "observe"


def prepare_field_items(
    fields: Mapping[str, str | None],
) -> list[tuple[str, str]]:
    """Skip empties; dedupe identical text (keep first source label)."""
    seen: set[str] = set()
    items: list[tuple[str, str]] = []
    for source, raw in fields.items():
        text = (raw or "").strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        items.append((str(source), text))
    return items


def _handle_intervention(
    *,
    source: str,
    direction: Direction,
    mode: str,
    trip_id: str | None,
    safety_latency_ms: int | None = None,
) -> None:
    out_mode = safety_output_mode() if direction == "output" else None
    log_safety_metric(
        direction=direction,
        source=source,
        mode=mode,
        intervened=True,
        trip_id=trip_id,
        safety_latency_ms=safety_latency_ms,
        output_mode=out_mode,
    )
    if direction == "output" and safety_output_mode() == "observe":
        return
    raise SafetyRejected(source, "content rejected by safety gate")


class NoopSafetyGate:
    def check_text(
        self,
        text: str,
        *,
        source: str,
        direction: Direction = "input",
        trip_id: str | None = None,
    ) -> None:
        return None

    def check_texts(
        self,
        fields: Mapping[str, str | None],
        *,
        direction: Direction = "input",
        trip_id: str | None = None,
    ) -> None:
        return None


class KeywordSafetyGate:
    def __init__(self, deny_phrases: tuple[str, ...] | None = None) -> None:
        self._deny = tuple(p.lower() for p in (deny_phrases or _DEFAULT_DENY))
        self.mode = "keyword"

    def _blocked_source(self, text: str) -> str | None:
        lowered = text.lower()
        for phrase in self._deny:
            if phrase in lowered:
                return phrase
        return None

    def check_text(
        self,
        text: str,
        *,
        source: str,
        direction: Direction = "input",
        trip_id: str | None = None,
    ) -> None:
        if not (text or "").strip():
            return
        started = time.perf_counter()
        if self._blocked_source(text) is not None:
            _handle_intervention(
                source=source,
                direction=direction,
                mode=self.mode,
                trip_id=trip_id,
                safety_latency_ms=max(
                    0, int((time.perf_counter() - started) * 1000)
                ),
            )

    def check_texts(
        self,
        fields: Mapping[str, str | None],
        *,
        direction: Direction = "input",
        trip_id: str | None = None,
    ) -> None:
        started = time.perf_counter()
        for source, text in prepare_field_items(fields):
            if self._blocked_source(text) is not None:
                _handle_intervention(
                    source=source,
                    direction=direction,
                    mode=self.mode,
                    trip_id=trip_id,
                    safety_latency_ms=max(
                        0, int((time.perf_counter() - started) * 1000)
                    ),
                )
                return


def check_texts(
    gate: SafetyGate,
    fields: Mapping[str, str | None],
    *,
    direction: Direction = "input",
    trip_id: str | None = None,
) -> None:
    """Batch-friendly entry: prefers gate.check_texts (one ApplyGuardrail for Bedrock)."""
    gate.check_texts(fields, direction=direction, trip_id=trip_id)


def get_safety_gate() -> SafetyGate:
    mode = safety_mode()
    if mode in {"off", "noop", "none"}:
        return NoopSafetyGate()
    if mode in {"bedrock", "guardrails"}:
        from safety.bedrock import BedrockGuardrailsSafetyGate

        return BedrockGuardrailsSafetyGate.from_env()
    if mode in {"keyword", "keywords"}:
        return KeywordSafetyGate()
    raise ApiError(
        500,
        f"Unknown SAFETY_MODE={mode!r} (expected keyword|bedrock|off)",
        code="safety_misconfigured",
    )
