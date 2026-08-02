"""Bedrock Guardrails safety gate — batched ApplyGuardrail + OUTPUT observe/enforce."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Mapping
from typing import Any

import boto3

from http_utils import ApiError
from safety.gate import (
    Direction,
    SafetyCheckUnavailable,
    SafetyRejected,
    _handle_intervention,
    prepare_field_items,
    safety_output_mode,
)
from safety.metrics import log_safety_metric

logger = logging.getLogger(__name__)

# Soft cap per ApplyGuardrail request (chars); chunk further if needed.
_MAX_BATCH_CHARS = 20_000


def _bedrock_region() -> str:
    return (
        os.getenv("AWS_REGION", "").strip()
        or os.getenv("AWS_DEFAULT_REGION", "").strip()
        or "us-east-1"
    )


def _chunk_items(
    items: list[tuple[str, str]],
) -> list[list[tuple[str, str]]]:
    """Split into batches under _MAX_BATCH_CHARS total text."""
    batches: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    size = 0
    for source, text in items:
        piece = len(text)
        if current and size + piece > _MAX_BATCH_CHARS:
            batches.append(current)
            current = []
            size = 0
        # Oversized single field: truncate for the gate (still labels source).
        if piece > _MAX_BATCH_CHARS:
            text = text[:_MAX_BATCH_CHARS]
            piece = len(text)
        current.append((source, text))
        size += piece
    if current:
        batches.append(current)
    return batches


class BedrockGuardrailsSafetyGate:
    """Calls Bedrock ApplyGuardrail for non-empty traveler / AI text."""

    def __init__(self, guardrail_id: str, version: str) -> None:
        self.guardrail_id = guardrail_id
        self.version = version
        self.mode = "bedrock"
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

    def check_text(
        self,
        text: str,
        *,
        source: str,
        direction: Direction = "input",
        trip_id: str | None = None,
    ) -> None:
        self.check_texts(
            {source: text},
            direction=direction,
            trip_id=trip_id,
        )

    def check_texts(
        self,
        fields: Mapping[str, str | None],
        *,
        direction: Direction = "input",
        trip_id: str | None = None,
    ) -> None:
        items = prepare_field_items(fields)
        if not items:
            return

        started = time.perf_counter()
        bedrock_source = "OUTPUT" if direction == "output" else "INPUT"
        try:
            for batch in _chunk_items(items):
                self._apply_batch(
                    batch,
                    bedrock_source=bedrock_source,
                    direction=direction,
                    trip_id=trip_id,
                    started=started,
                )
        except SafetyRejected:
            raise
        except SafetyCheckUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            self._on_transport_error(
                exc,
                direction=direction,
                trip_id=trip_id,
                started=started,
                source=items[0][0],
            )

    def _apply_batch(
        self,
        batch: list[tuple[str, str]],
        *,
        bedrock_source: str,
        direction: Direction,
        trip_id: str | None,
        started: float,
    ) -> None:
        content = [{"text": {"text": text}} for _, text in batch]
        response = self._apply_with_retry(
            bedrock_source=bedrock_source,
            content=content,
            direction=direction,
            trip_id=trip_id,
            started=started,
            source=batch[0][0],
        )
        if response.get("action") != "GUARDRAIL_INTERVENED":
            return
        # Prefer first field label; assessments may not map cleanly.
        source = batch[0][0]
        latency = max(0, int((time.perf_counter() - started) * 1000))
        _handle_intervention(
            source=source,
            direction=direction,
            mode=self.mode,
            trip_id=trip_id,
            safety_latency_ms=latency,
        )

    def _apply_with_retry(
        self,
        *,
        bedrock_source: str,
        content: list[dict[str, Any]],
        direction: Direction,
        trip_id: str | None,
        started: float,
        source: str,
    ) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                return self.client.apply_guardrail(
                    guardrailIdentifier=self.guardrail_id,
                    guardrailVersion=self.version,
                    source=bedrock_source,
                    content=content,
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt == 0:
                    logger.warning(
                        "ApplyGuardrail attempt %s failed: %s",
                        attempt + 1,
                        type(exc).__name__,
                    )
                    continue
        assert last_exc is not None
        self._on_transport_error(
            last_exc,
            direction=direction,
            trip_id=trip_id,
            started=started,
            source=source,
        )
        return {"action": "NONE"}

    def _on_transport_error(
        self,
        exc: Exception,
        *,
        direction: Direction,
        trip_id: str | None,
        started: float,
        source: str,
    ) -> None:
        latency = max(0, int((time.perf_counter() - started) * 1000))
        log_safety_metric(
            direction=direction,
            source=source,
            mode=self.mode,
            intervened=False,
            trip_id=trip_id,
            safety_latency_ms=latency,
            output_mode=safety_output_mode() if direction == "output" else None,
            unavailable=True,
            extra={"error_type": type(exc).__name__},
        )
        if direction == "output":
            # Fail-open: do not discard a finished plan on Guardrail outage.
            logger.warning(
                "OUTPUT safety check unavailable (%s); persisting without block",
                type(exc).__name__,
            )
            return
        raise SafetyCheckUnavailable(
            "safety check unavailable; try again shortly"
        ) from exc
