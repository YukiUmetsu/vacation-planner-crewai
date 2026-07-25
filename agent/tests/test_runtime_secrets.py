"""Tests for AgentCore secret → env helpers."""

from __future__ import annotations

import os
import sys
import types

import runtime_secrets as secrets


def test_ensure_amap_uses_plaintext(monkeypatch) -> None:
    monkeypatch.setenv("AMAP_WEB_KEY", "plain-key")
    monkeypatch.delenv("AMAP_WEB_SECRET_ARN", raising=False)
    assert secrets.ensure_amap_web_key() == "plain-key"


def test_ensure_amap_uses_alt_plain(monkeypatch) -> None:
    monkeypatch.delenv("AMAP_WEB_KEY", raising=False)
    monkeypatch.setenv("AMAP_KEY", "alt-key")
    monkeypatch.delenv("AMAP_WEB_SECRET_ARN", raising=False)
    assert secrets.ensure_amap_web_key() == "alt-key"
    assert os.getenv("AMAP_WEB_KEY") == "alt-key"


def test_ensure_amap_from_secret_arn(monkeypatch) -> None:
    monkeypatch.delenv("AMAP_WEB_KEY", raising=False)
    monkeypatch.delenv("AMAP_KEY", raising=False)
    monkeypatch.setenv(
        "AMAP_WEB_SECRET_ARN",
        "arn:aws:secretsmanager:us-east-1:1:secret:amap",
    )

    class _FakeClient:
        def get_secret_value(self, SecretId: str):
            assert "amap" in SecretId
            return {"SecretString": '{"api_key":"from-sm"}'}

    fake_boto3 = types.SimpleNamespace(
        client=lambda name: _FakeClient() if name == "secretsmanager" else None
    )
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    assert secrets.ensure_amap_web_key() == "from-sm"
    assert os.getenv("AMAP_WEB_KEY") == "from-sm"


def test_parse_plain_secret_string() -> None:
    assert (
        secrets._parse_secret_string("raw-key", preferred_keys=("api_key",))
        == "raw-key"
    )


def test_ensure_serper_from_secret_arn(monkeypatch) -> None:
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.setenv("SERPER_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:1:secret:serper")

    class _FakeClient:
        def get_secret_value(self, SecretId: str):
            return {"SecretString": "serper-plain"}

    fake_boto3 = types.SimpleNamespace(client=lambda name: _FakeClient())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    assert secrets.ensure_serper_api_key() == "serper-plain"
    assert os.getenv("SERPER_API_KEY") == "serper-plain"
