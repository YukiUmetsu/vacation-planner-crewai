"""Contract tests for AgentCore BFF client (mocked AWS)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from agentcore import client as agentcore_client
from http_utils import ApiError


class _FakeBody:
    def __init__(self, payload: dict[str, Any] | bytes) -> None:
        if isinstance(payload, bytes):
            self._raw = payload
        else:
            self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw


def test_invoke_agent_requires_runtime_arn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_RUNTIME_ARN", raising=False)
    monkeypatch.delenv("AGENTCORE_ARN", raising=False)
    with pytest.raises(ApiError) as exc:
        agentcore_client.invoke_agent({"crew": "day_plan", "inputs": {}})
    assert exc.value.status_code == 500
    assert exc.value.code == "agent_misconfigured"


def test_invoke_agent_reads_configured_arn_and_parses_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:123:runtime/demo")

    captured: dict[str, Any] = {}

    class FakeBotoClient:
        def invoke_agent_runtime(self, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {
                "response": _FakeBody(
                    {
                        "day_index": 1,
                        "theme": "Test",
                        "overnight_city": "Tokyo",
                        "places": [{"name": "A", "place_key": "a"}],
                    }
                )
            }

    monkeypatch.setattr(
        agentcore_client.boto3,
        "client",
        lambda *args, **kwargs: FakeBotoClient(),
    )

    payload = {"crew": "day_plan", "inputs": {"overnight_city": "Tokyo"}}
    out = agentcore_client.invoke_agent(payload)

    assert captured["agentRuntimeArn"].endswith("runtime/demo")
    assert json.loads(captured["payload"].decode("utf-8")) == payload
    assert out["overnight_city"] == "Tokyo"
    assert out["places"][0]["place_key"] == "a"


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("invalid_payload", 400),
        ("invalid_crew", 400),
        ("crew_not_found", 502),
        ("crew_failed", 502),
        ("unknown_code", 502),
    ],
)
def test_invoke_agent_maps_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    status: int,
) -> None:
    monkeypatch.setenv("AGENT_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:123:runtime/demo")

    class FakeBotoClient:
        def invoke_agent_runtime(self, **kwargs: Any) -> dict[str, Any]:
            return {"response": _FakeBody({"error": "boom", "code": code})}

    monkeypatch.setattr(
        agentcore_client.boto3,
        "client",
        lambda *args, **kwargs: FakeBotoClient(),
    )

    with pytest.raises(ApiError) as exc:
        agentcore_client.invoke_agent({"crew": "day_plan", "inputs": {}})
    assert exc.value.status_code == status
    assert exc.value.code == code
    if status >= 500:
        assert "boom" not in exc.value.message
        assert "Failed" not in exc.value.message or "try again" in exc.value.message.lower()
        assert "try again" in exc.value.message.lower()
    else:
        assert exc.value.message == "boom"


def test_invoke_agent_raises_on_missing_response_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:123:runtime/demo")

    class FakeBotoClient:
        def invoke_agent_runtime(self, **kwargs: Any) -> dict[str, Any]:
            return {}

    monkeypatch.setattr(
        agentcore_client.boto3,
        "client",
        lambda *args, **kwargs: FakeBotoClient(),
    )

    with pytest.raises(ApiError) as exc:
        agentcore_client.invoke_agent({"crew": "day_plan", "inputs": {}})
    assert exc.value.status_code == 502
    assert exc.value.code == "agent_bad_response"
    assert exc.value.retryable is False


def test_invoke_agent_marks_sdk_failures_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:123:runtime/demo")

    class FakeBotoClient:
        def invoke_agent_runtime(self, **kwargs: Any) -> dict[str, Any]:
            raise TimeoutError("slow")

    monkeypatch.setattr(
        agentcore_client.boto3,
        "client",
        lambda *args, **kwargs: FakeBotoClient(),
    )

    with pytest.raises(ApiError) as exc:
        agentcore_client.invoke_agent({"crew": "day_plan", "inputs": {}})
    assert exc.value.code == "agent_invoke_failed"
    assert exc.value.retryable is True


def test_invoke_agent_marks_access_denied_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:123:runtime/demo")
    monkeypatch.delenv("AUTH_MODE", raising=False)

    class AccessDeniedException(Exception):
        pass

    class FakeBotoClient:
        def invoke_agent_runtime(self, **kwargs: Any) -> dict[str, Any]:
            raise AccessDeniedException("nope")

    monkeypatch.setattr(
        agentcore_client.boto3,
        "client",
        lambda *args, **kwargs: FakeBotoClient(),
    )

    with pytest.raises(ApiError) as exc:
        agentcore_client.invoke_agent({"crew": "day_plan", "inputs": {}})
    assert exc.value.code == "agent_invoke_failed"
    assert exc.value.retryable is False


def test_invoke_agent_access_denied_is_auth_failed_in_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:123:runtime/demo")
    monkeypatch.setenv("AUTH_MODE", "dev")

    class AccessDeniedException(Exception):
        pass

    class FakeBotoClient:
        def invoke_agent_runtime(self, **kwargs: Any) -> dict[str, Any]:
            raise AccessDeniedException("nope")

    monkeypatch.setattr(
        agentcore_client.boto3,
        "client",
        lambda *args, **kwargs: FakeBotoClient(),
    )

    with pytest.raises(ApiError) as exc:
        agentcore_client.invoke_agent({"crew": "day_plan", "inputs": {}})
    assert exc.value.code == "agent_auth_failed"
    assert exc.value.retryable is False


@pytest.mark.parametrize(
    ("code", "retryable"),
    [
        ("invalid_payload", False),
        ("crew_failed", False),
    ],
)
def test_envelope_errors_are_not_retryable(
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    retryable: bool,
) -> None:
    monkeypatch.setenv("AGENT_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:123:runtime/demo")

    class FakeBotoClient:
        def invoke_agent_runtime(self, **kwargs: Any) -> dict[str, Any]:
            return {"response": _FakeBody({"error": "boom", "code": code})}

    monkeypatch.setattr(
        agentcore_client.boto3,
        "client",
        lambda *args, **kwargs: FakeBotoClient(),
    )

    with pytest.raises(ApiError) as exc:
        agentcore_client.invoke_agent({"crew": "day_plan", "inputs": {}})
    assert exc.value.retryable is retryable
