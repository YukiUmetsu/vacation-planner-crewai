"""Invoke AgentCore Runtime from the BFF (server IAM only)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
from http_utils import ApiError, client_facing_message

logger = logging.getLogger(__name__)

# Must match Terraform: infra/api/main.tf → AGENT_RUNTIME_ARN
_ARN_ENV = "AGENT_RUNTIME_ARN"

# Entrypoint {error, code} → HTTP status for the API Gateway client.
_ENVELOPE_STATUS: dict[str, int] = {
    "invalid_payload": 400,
    "invalid_crew": 400,
    "crew_not_found": 502,
    "crew_failed": 502,
}

# SDK / IAM / config failures that will not recover on Lambda Event retry.
_TERMINAL_INVOKE_ERROR_NAMES = frozenset(
    {
        "AccessDeniedException",
        "UnauthorizedException",
        "ValidationException",
        "ResourceNotFoundException",
        "InvalidParameterException",
        "InvalidRequestException",
    }
)


def _is_retryable_invoke_error(exc: BaseException) -> bool:
    """True for throttle / timeout / 5xx-style InvokeAgentRuntime failures."""
    name = type(exc).__name__
    if name in _TERMINAL_INVOKE_ERROR_NAMES:
        return False

    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        err = response.get("Error") or {}
        code = str(err.get("Code") or "")
        if code in _TERMINAL_INVOKE_ERROR_NAMES:
            return False
        status = (response.get("ResponseMetadata") or {}).get("HTTPStatusCode")
        if status is not None:
            try:
                code_i = int(status)
            except (TypeError, ValueError):
                return True
            # 429 and 5xx → retry; other 4xx → terminal.
            if code_i == 429 or code_i >= 500:
                return True
            if 400 <= code_i < 500:
                return False
    return True


def _raise_public(
    status: int,
    *,
    code: str,
    detail: str,
    retryable: bool = False,
) -> None:
    logger.warning(
        "API_ERROR status=%s code=%s msg=%r source=agentcore",
        status,
        code,
        detail,
    )
    raise ApiError(
        status,
        client_facing_message(status_code=status, code=code, detail=detail),
        code=code,
        retryable=retryable,
    )


def invoke_agent(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Call InvokeAgentRuntime with ``{crew, inputs}`` matching agent/invoke_payload.py.

    Returns the crew output dict (DayPlan / CityRoute shaped JSON).
    Raises ApiError for misconfiguration, bad envelopes, and transport failures.
    """
    arn = os.environ.get(_ARN_ENV, "").strip()
    if not arn:
        _raise_public(
            500,
            code="agent_misconfigured",
            detail=f"{_ARN_ENV} environment variable is not set",
        )

    body = json.dumps(payload).encode("utf-8")
    try:
        client = boto3.client("bedrock-agentcore")
        response = client.invoke_agent_runtime(
            agentRuntimeArn=arn,
            payload=body,
            contentType="application/json",
            accept="application/json",
        )
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001 — map AWS SDK errors at the BFF boundary
        # Includes UnknownServiceError when Lambda's boto3/botocore is too old
        # for bedrock-agentcore, plus IAM / transport failures.
        detail = f"AgentCore invoke failed: {type(exc).__name__}: {exc}"
        code = "agent_invoke_failed"
        # Local AUTH_MODE=dev: surface auth misconfig instead of a vague 502.
        if (
            os.getenv("AUTH_MODE", "").strip().lower() == "dev"
            and type(exc).__name__ == "AccessDeniedException"
        ):
            code = "agent_auth_failed"
            detail = (
                "AgentCore AccessDenied — local API is not using valid AWS credentials. "
                "Restart ./scripts/dev.sh with a working AWS profile "
                "(do not export AWS_ACCESS_KEY_ID=local)."
            )
        _raise_public(
            502,
            code=code,
            detail=detail,
            retryable=_is_retryable_invoke_error(exc),
        )

    stream = response.get("response")
    if stream is None:
        _raise_public(
            502,
            code="agent_bad_response",
            detail="AgentCore response missing 'response' body",
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
        _raise_public(
            502,
            code="agent_bad_response",
            detail=f"AgentCore returned non-JSON body: {exc}",
        )

    if not isinstance(data, dict):
        _raise_public(
            502,
            code="agent_bad_response",
            detail=f"AgentCore returned non-object JSON: {type(data).__name__}",
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
        detail = str(data["error"])
        _raise_public(status, code=code, detail=detail)

    return data
