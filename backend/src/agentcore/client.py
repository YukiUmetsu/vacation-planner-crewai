"""Invoke AgentCore Runtime from the BFF (server IAM only)."""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
from http_utils import ApiError

# Must match Terraform: infra/api/main.tf → AGENT_RUNTIME_ARN
_ARN_ENV = "AGENT_RUNTIME_ARN"

# Entrypoint {error, code} → HTTP status for the API Gateway client.
_ENVELOPE_STATUS: dict[str, int] = {
    "invalid_payload": 400,
    "invalid_crew": 400,
    "crew_not_found": 502,
    "crew_failed": 502,
}


def invoke_agent(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Call InvokeAgentRuntime with ``{crew, inputs}`` matching agent/invoke_payload.py.

    Returns the crew output dict (DayPlan / CityRoute shaped JSON).
    Raises ApiError for misconfiguration, bad envelopes, and transport failures.
    """
    arn = os.environ.get(_ARN_ENV, "").strip()
    if not arn:
        raise ApiError(
            500,
            f"{_ARN_ENV} environment variable is not set",
            code="agent_misconfigured",
        )

    client = boto3.client("bedrock-agentcore")
    body = json.dumps(payload).encode("utf-8")
    try:
        response = client.invoke_agent_runtime(
            agentRuntimeArn=arn,
            payload=body,
            contentType="application/json",
            accept="application/json",
        )
    except Exception as exc:  # noqa: BLE001 — map AWS SDK errors at the BFF boundary
        raise ApiError(
            502,
            f"AgentCore invoke failed: {type(exc).__name__}",
            code="agent_invoke_failed",
        ) from exc

    stream = response.get("response")
    if stream is None:
        raise ApiError(
            502,
            "AgentCore response missing 'response' body",
            code="agent_bad_response",
        )

    raw = stream.read() if hasattr(stream, "read") else stream
    if isinstance(raw, memoryview):
        raw = raw.tobytes()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8")
    else:
        text = str(raw)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ApiError(
            502,
            "AgentCore returned non-JSON body",
            code="agent_bad_response",
        ) from exc

    if not isinstance(data, dict):
        raise ApiError(
            502,
            f"AgentCore returned non-object JSON: {type(data).__name__}",
            code="agent_bad_response",
        )

    # Entrypoint error envelope: { "error": "...", "code": "..." }
    # Success shapes: DayPlan (places), CityRoute (cities), Place (place_key).
    if (
        "error" in data
        and "code" in data
        and "places" not in data
        and "cities" not in data
        and "place_key" not in data
    ):
        code = str(data.get("code") or "agent_error")
        status = _ENVELOPE_STATUS.get(code, 502)
        raise ApiError(status, str(data["error"]), code=code)

    return data
