"""Auth mode behavior."""

from __future__ import annotations

import pytest

from auth import auth_mode, get_user_sub
from http_utils import ApiError


def test_auth_mode_defaults_to_cognito(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTH_MODE", raising=False)
    assert auth_mode() == "cognito"
    with pytest.raises(ApiError) as exc:
        get_user_sub({"headers": {"x-dev-user-sub": "attacker"}})
    assert exc.value.status_code == 401
    assert exc.value.code == "unauthorized"


def test_cognito_reads_apigw_jwt_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "cognito")
    event = {
        "requestContext": {
            "authorizer": {"jwt": {"claims": {"sub": "cognito-user-123"}}}
        },
        "headers": {},
    }
    assert get_user_sub(event) == "cognito-user-123"


def test_dev_auth_only_when_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    assert get_user_sub({"headers": {"x-dev-user-sub": "alice"}}) == "alice"
