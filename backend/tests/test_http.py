"""HTTP helper / handler edge cases."""

from __future__ import annotations

import json
from typing import Any

import pytest

from handler import handler
from http_utils import ApiError, parse_body
from routes import trips as trip_routes


def test_parse_body_rejects_invalid_json() -> None:
    with pytest.raises(ApiError) as exc:
        parse_body({"body": "{not-json"})
    assert exc.value.status_code == 400
    assert exc.value.code == "invalid_json"


def test_parse_body_rejects_non_object_json() -> None:
    with pytest.raises(ApiError) as exc:
        parse_body({"body": "[1,2,3]"})
    assert exc.value.status_code == 400


def test_handler_invalid_json_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    event = {
        "requestContext": {"http": {"method": "POST"}},
        "rawPath": "/trips",
        "headers": {"x-dev-user-sub": "u"},
        "body": "{bad",
    }
    resp = handler(event)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body["code"] == "invalid_json"


def test_handler_500_does_not_leak_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")

    def boom(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("secret db password=hunter2")

    monkeypatch.setattr(trip_routes, "list_trips", boom)
    resp = handler(
        {
            "requestContext": {"http": {"method": "GET"}},
            "rawPath": "/trips",
            "headers": {"x-dev-user-sub": "u"},
        }
    )
    assert resp["statusCode"] == 500
    body = json.loads(resp["body"])
    assert body["code"] == "internal_error"
    assert body["error"] == "internal server error"
    assert "hunter2" not in resp["body"]
