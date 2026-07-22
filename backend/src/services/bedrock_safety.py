"""Bedrock Guardrails safety gate — env wiring + LEARNING stub for ApplyGuardrail."""

from __future__ import annotations

import os

from http_utils import ApiError

import boto3
from services.safety import SafetyRejected

class BedrockGuardrailsSafetyGate:
    """Calls Bedrock ApplyGuardrail once ``check_text`` is implemented."""

    def __init__(self, guardrail_id: str, version: str) -> None:
        self.guardrail_id = guardrail_id
        self.version = version
        self.client = boto3.client("bedrock-runtime")

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
        if len(text.strip()) == 0:
            return

        response = self.client.apply_guardrail(
            guardrailIdentifier=self.guardrail_id,
            guardrailVersion=self.version,
            source='INPUT',
            content=[{'text': {'text': text}}],
        )
        if response['action'] == 'GUARDRAIL_INTERVENED':
            raise SafetyRejected(source, "content rejected by safety gate")
