"""Bedrock Guardrails safety gate — env wiring + ApplyGuardrail."""

from __future__ import annotations

import os
from typing import Any

import boto3

from http_utils import ApiError
from safety.gate import SafetyRejected


def _bedrock_region() -> str:
    return (
        os.getenv("AWS_REGION", "").strip()
        or os.getenv("AWS_DEFAULT_REGION", "").strip()
        or "us-east-1"
    )


class BedrockGuardrailsSafetyGate:
    """Calls Bedrock ApplyGuardrail for non-empty traveler text."""

    def __init__(self, guardrail_id: str, version: str) -> None:
        self.guardrail_id = guardrail_id
        self.version = version
        self._client: Any | None = None

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = boto3.client(
                "bedrock-runtime",
                region_name=_bedrock_region(),
            )
        return self._client

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
            source="INPUT",
            content=[{"text": {"text": text}}],
        )
        if response["action"] == "GUARDRAIL_INTERVENED":
            raise SafetyRejected(source, "content rejected by safety gate")
