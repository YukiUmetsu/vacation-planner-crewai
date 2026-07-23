"""Unit tests for the local HTTP ↔ Lambda event adapter."""

from __future__ import annotations

import json
from typing import Any

from local_http import build_lambda_event, lambda_result_to_http, strip_api_prefix


def test_strip_api_prefix_for_vite_proxy() -> None:
    assert strip_api_prefix("/api/trips") == "/trips"
    assert strip_api_prefix("/api/trips/abc/propose-cities") == "/trips/abc/propose-cities"
    assert strip_api_prefix("/trips") == "/trips"
    assert strip_api_prefix("/api") == "/"
    assert strip_api_prefix("/api/") == "/"


def test_build_lambda_event_shape() -> None:
    event = build_lambda_event(
        method="post",
        path="/api/trips",
        headers={"Content-Type": "application/json", "X-Dev-User-Sub": "u1"},
        body=b'{"origin":"Chicago"}',
        query="",
    )
    assert event["rawPath"] == "/trips"
    assert event["requestContext"]["http"]["method"] == "POST"
    assert event["headers"]["x-dev-user-sub"] == "u1"
    assert event["body"] == '{"origin":"Chicago"}'
    assert event["isBase64Encoded"] is False


def test_lambda_result_to_http() -> None:
    status, headers, payload = lambda_result_to_http(
        {
            "statusCode": 201,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"ok": True}),
        }
    )
    assert status == 201
    assert headers["content-type"] == "application/json"
    assert json.loads(payload.decode("utf-8")) == {"ok": True}


def test_make_request_handler_invokes_lambda() -> None:
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer
    from threading import Thread

    from local_http import make_request_handler

    calls: list[dict[str, Any]] = []

    def fake_handler(event: dict[str, Any], _ctx: Any) -> dict[str, Any]:
        calls.append(event)
        return {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"path": event["rawPath"]}),
        }

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_request_handler(fake_handler))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        conn = HTTPConnection(host, port, timeout=2)
        conn.request(
            "GET",
            "/api/trips",
            headers={"x-dev-user-sub": "u"},
        )
        resp = conn.getresponse()
        body = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 200
        assert body["path"] == "/trips"
        assert calls[0]["rawPath"] == "/trips"
        conn.close()

        conn = HTTPConnection(host, port, timeout=2)
        conn.request("DELETE", "/api/trips/trip-1", headers={"x-dev-user-sub": "u"})
        resp = conn.getresponse()
        body = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 200
        assert body["path"] == "/trips/trip-1"
        assert calls[1]["requestContext"]["http"]["method"] == "DELETE"
        conn.close()
    finally:
        server.shutdown()
        server.server_close()


def test_invalid_content_length_returns_400_json() -> None:
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer
    from threading import Thread

    from local_http import make_request_handler

    def boom(_event: dict[str, Any], _ctx: Any) -> dict[str, Any]:
        raise AssertionError("handler should not run")

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_request_handler(boom))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        conn = HTTPConnection(host, port, timeout=2)
        conn.putrequest("POST", "/api/trips")
        conn.putheader("Content-Length", "not-a-number")
        conn.putheader("Content-Type", "application/json")
        conn.endheaders(b"{}")
        resp = conn.getresponse()
        body = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 400
        assert body["code"] == "invalid_request"
        assert "content-length" in body["error"]
        conn.close()
    finally:
        server.shutdown()
        server.server_close()


def test_invalid_utf8_body_returns_400_json() -> None:
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer
    from threading import Thread

    from local_http import make_request_handler

    def boom(_event: dict[str, Any], _ctx: Any) -> dict[str, Any]:
        raise AssertionError("handler should not run")

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_request_handler(boom))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        bad = b"\xff\xfe not utf-8"
        conn = HTTPConnection(host, port, timeout=2)
        conn.putrequest("POST", "/api/trips")
        conn.putheader("Content-Length", str(len(bad)))
        conn.putheader("Content-Type", "application/json")
        conn.endheaders(bad)
        resp = conn.getresponse()
        body = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 400
        assert body["code"] == "invalid_request"
        assert "UTF-8" in body["error"]
        conn.close()
    finally:
        server.shutdown()
        server.server_close()


def test_parse_content_length_rejects_garbage() -> None:
    import pytest

    from local_http import parse_content_length

    with pytest.raises(ValueError, match="content-length"):
        parse_content_length({"content-length": "abc"})
