"""Bedrock Guardrails safety gate — env wiring + LEARNING stub for ApplyGuardrail."""

from __future__ import annotations

import os

from http_utils import ApiError


class BedrockGuardrailsSafetyGate:
    """Calls Bedrock ApplyGuardrail once ``check_text`` is implemented."""

    def __init__(self, guardrail_id: str, version: str) -> None:
        self.guardrail_id = guardrail_id
        self.version = version

    @classmethod
    def from_env(cls) -> BedrockGuardrailsSafetyGate:
        guardrail_id = os.getenv("BEDROCK_GUARDRAIL_ID", "").strip()
        if not guardrail_id:
            raise ApiError(
                500,
                "BEDROCK_GUARDRAIL_ID environment variable is not set",
                code="safety_misconfigured",
            )
        version = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT").strip() or "DRAFT"
        return cls(guardrail_id, version)

    def check_text(self, text: str, *, source: str) -> None:
        """LEARNING: call ``bedrock:ApplyGuardrail`` and map intervene → SafetyRejected."""
        _ = (text, source)
        raise ApiError(
            500,
            "BedrockGuardrailsSafetyGate.check_text is not implemented yet "
            f"(guardrail_id={self.guardrail_id!r}, version={self.version!r})",
            code="safety_not_implemented",
        )
