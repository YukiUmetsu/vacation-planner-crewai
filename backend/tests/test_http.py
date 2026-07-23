"""HTTP helper / handler edge cases."""

from __future__ import annotations

import json
import logging
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


def test_handler_invalid_json_returns_400(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    event = {
        "requestContext": {"http": {"method": "POST"}},
        "rawPath": "/trips",
        "headers": {"x-dev-user-sub": "u"},
        "body": "{bad",
    }
    with caplog.at_level(logging.WARNING):
        resp = handler(event)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body["code"] == "invalid_json"
    assert any("API_ERROR" in r.message and "invalid_json" in r.message for r in caplog.records)


def test_handler_api_error_4xx_is_logged(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")

    def boom(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise ApiError(
            400,
            "route has overlapping city coverage on day 3",
            code="route_overlap",
        )

    monkeypatch.setattr(trip_routes, "confirm_cities", boom)
    with caplog.at_level(logging.WARNING):
        resp = handler(
            {
                "requestContext": {"http": {"method": "PUT"}},
                "rawPath": "/trips/t1/cities",
                "headers": {"x-dev-user-sub": "u"},
                "body": "{}",
            }
        )
    assert resp["statusCode"] == 400
    assert any(
        "API_ERROR" in r.message
        and "route_overlap" in r.message
        and "overlapping" in r.message
        for r in caplog.records
    )


def test_handler_500_does_not_leak_exception(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")

    def boom(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("secret db password=hunter2")

    monkeypatch.setattr(trip_routes, "list_trips", boom)
    with caplog.at_level(logging.ERROR):
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
    assert body["error"] == "Something went wrong. Please try again."
    assert "hunter2" not in resp["body"]
    assert any("API_ERROR" in r.message and "internal_error" in r.message for r in caplog.records)
    assert "hunter2" in caplog.text
