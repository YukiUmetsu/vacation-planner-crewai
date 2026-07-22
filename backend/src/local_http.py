"""Map plain HTTP requests to API Gateway HTTP API v2 Lambda events.

Used only for local development (``scripts/local_api.py``). Production traffic
goes through API Gateway → Lambda and never imports this module.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlparse


HandlerFn = Callable[[dict[str, Any], Any], dict[str, Any]]

# Vite proxies ``/api/*`` → ``:8787/api/*``. Lambda routes are ``/trips…``.
_API_PREFIX = "/api"


def strip_api_prefix(path: str) -> str:
    """Normalize a proxied or direct path to the Lambda ``rawPath`` shape."""
    if not path.startswith("/"):
        path = f"/{path}"
    if path == _API_PREFIX or path.startswith(f"{_API_PREFIX}/"):
        path = path[len(_API_PREFIX) :] or "/"
    return path.rstrip("/") or "/"


def _json_error(status: int, message: str, code: str) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"error": message, "code": code}),
    }


def parse_content_length(headers: Mapping[str, str]) -> int:
    raw = headers.get("content-length") or headers.get("Content-Length") or "0"
    try:
        length = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid content-length") from exc
    if length < 0:
        raise ValueError("invalid content-length")
    return length


def build_lambda_event(
    *,
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: bytes | None,
    query: str = "",
) -> dict[str, Any]:
    """Build an API Gateway HTTP API (payload format 2.0)–shaped event."""
    raw_path = strip_api_prefix(path)
    header_map = {str(k).lower(): str(v) for k, v in headers.items() if v is not None}

    event: dict[str, Any] = {
        "version": "2.0",
        "routeKey": f"{method.upper()} {raw_path}",
        "rawPath": raw_path,
        "rawQueryString": query.lstrip("?"),
        "headers": header_map,
        "requestContext": {
            "http": {
                "method": method.upper(),
                "path": raw_path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": header_map.get("user-agent", "local-api"),
            }
        },
        "isBase64Encoded": False,
    }

    if query:
        # parse_qs keeps lists; Lambda often exposes first value — keep lists for honesty.
        event["queryStringParameters"] = {
            k: v[0] if len(v) == 1 else v for k, v in parse_qs(query.lstrip("?")).items()
        }

    if body:
        try:
            event["body"] = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("request body is not valid UTF-8") from exc
    else:
        event["body"] = None

    return event


def lambda_result_to_http(result: dict[str, Any]) -> tuple[int, dict[str, str], bytes]:
    """Translate a Lambda proxy response dict into status, headers, and body bytes."""
    status = int(result.get("statusCode") or 500)
    raw_headers = result.get("headers") or {}
    headers = {str(k).lower(): str(v) for k, v in raw_headers.items()}
    headers.setdefault("content-type", "application/json")

    body = result.get("body")
    if body is None:
        payload = b""
    elif isinstance(body, bytes):
        payload = body
    else:
        payload = str(body).encode("utf-8")

    if result.get("isBase64Encoded"):
        import base64

        payload = base64.b64decode(payload)

    return status, headers, payload


def make_request_handler(invoke: HandlerFn) -> type[BaseHTTPRequestHandler]:
    """Return a ``BaseHTTPRequestHandler`` subclass that delegates to ``invoke``."""

    class LocalApiHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

        def _write_result(self, result: dict[str, Any]) -> None:
            status, headers, payload = lambda_result_to_http(result)
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        def _handle(self) -> None:
            try:
                parsed = urlparse(self.path)
                header_map = {str(k).lower(): str(v) for k, v in self.headers.items()}
                length = parse_content_length(header_map)
                raw_body = self.rfile.read(length) if length > 0 else None
                event = build_lambda_event(
                    method=self.command,
                    path=parsed.path,
                    headers=header_map,
                    body=raw_body,
                    query=parsed.query,
                )
            except ValueError as exc:
                self._write_result(_json_error(400, str(exc), "invalid_request"))
                return
            except Exception:  # noqa: BLE001 — adapter boundary
                self._write_result(
                    _json_error(500, "internal server error", "internal_error")
                )
                return

            try:
                result = invoke(event, None)
            except Exception:  # noqa: BLE001 — mirror Lambda boundary
                result = _json_error(500, "internal server error", "internal_error")

            self._write_result(result)

        def do_GET(self) -> None:  # noqa: N802
            self._handle()

        def do_POST(self) -> None:  # noqa: N802
            self._handle()

        def do_PUT(self) -> None:  # noqa: N802
            self._handle()

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._handle()

        def do_HEAD(self) -> None:  # noqa: N802
            self._handle()

    return LocalApiHandler
