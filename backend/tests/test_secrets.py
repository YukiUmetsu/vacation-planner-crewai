"""Unit tests for Secrets Manager resolution helpers."""

from __future__ import annotations

from typing import Any

import pytest

from services import secrets as secrets_mod


@pytest.fixture(autouse=True)
def _clear_secret_cache() -> None:
    secrets_mod.get_secret_string.cache_clear()


def test_resolve_prefers_plain_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "plain-key")
    monkeypatch.setenv("GOOGLE_PLACES_SECRET_ARN", "arn:aws:secretsmanager:…")
    assert (
        secrets_mod.resolve_secret(
            plain_env="GOOGLE_PLACES_API_KEY",
            arn_env="GOOGLE_PLACES_SECRET_ARN",
        )
        == "plain-key"
    )


def test_resolve_from_secret_arn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_PLACES_SECRET_ARN", "arn:example")

    def fake_get(secret_id: str) -> str:
        assert secret_id == "arn:example"
        return "sm-key"

    monkeypatch.setattr(secrets_mod, "get_secret_string", fake_get)
    assert (
        secrets_mod.resolve_secret(
            plain_env="GOOGLE_PLACES_API_KEY",
            arn_env="GOOGLE_PLACES_SECRET_ARN",
        )
        == "sm-key"
    )


def test_resolve_json_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("X_PLAIN", raising=False)
    monkeypatch.setenv("X_ARN", "arn:json")

    def fake_get(secret_id: str) -> str:
        return '{"client_id":"id","client_secret":"sekrit"}'

    monkeypatch.setattr(secrets_mod, "get_secret_string", fake_get)
    assert (
        secrets_mod.resolve_secret(
            plain_env="X_PLAIN",
            arn_env="X_ARN",
            json_key="client_secret",
        )
        == "sekrit"
    )


def test_resolve_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING", raising=False)
    monkeypatch.delenv("MISSING_ARN", raising=False)
    assert (
        secrets_mod.resolve_secret(
            plain_env="MISSING",
            arn_env="MISSING_ARN",
            fallback="fb",
        )
        == "fb"
    )
