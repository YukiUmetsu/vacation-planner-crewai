"""API Gateway request/response helpers."""

from __future__ import annotations

import base64
import json
import re
from decimal import Decimal
from typing import Any


_TRIP_ID_RE = re.compile(
    r"^/trips(?:/(?P<trip_id>[^/]+))?(?:/(?P<action>propose-cities|cities|plan-next-day))?/?$"
)
_DAY_ACTION_RE = re.compile(
    r"^/trips/(?P<trip_id>[^/]+)/days/(?P<day_index>\d+)/(?P<action>suggest-place)/?$"
)


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        code: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
        # When True (async worker): keep planning claim so Lambda Event can retry.
        self.retryable = retryable


def normalize_headers(event: dict[str, Any]) -> dict[str, str]:
    raw = event.get("headers") or {}
    return {str(k).lower(): str(v) for k, v in raw.items() if v is not None}


def request_method(event: dict[str, Any]) -> str:
    http = (event.get("requestContext") or {}).get("http") or {}
    method = http.get("method") or event.get("httpMethod") or "GET"
    return str(method).upper()


def request_path(event: dict[str, Any]) -> str:
    path = event.get("rawPath") or event.get("path") or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    # Strip stage prefix like /prod if present as sole first segment for local tests
    return path.rstrip("/") or "/"


def parse_route(path: str) -> tuple[str | None, str | None]:
    """Return (trip_id, action) for /trips routes. action None for collection/item."""
    match = _TRIP_ID_RE.match(path)
    if not match:
        return None, None
    return match.group("trip_id"), match.group("action")


def parse_day_action(path: str) -> tuple[str, int, str] | None:
    """Return (trip_id, day_index, action) for /trips/{id}/days/{n}/… routes."""
    match = _DAY_ACTION_RE.match(path)
    if not match:
        return None
    return match.group("trip_id"), int(match.group("day_index")), match.group("action")


def parse_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body")
    if body is None or body == "":
        return {}
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ApiError(400, "invalid base64 body", code="invalid_body") from exc
    if isinstance(body, dict):
        return body
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ApiError(400, "invalid JSON body", code="invalid_json") from exc
    if not isinstance(data, dict):
        raise ApiError(400, "JSON body must be an object", code="invalid_json")
    return data


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def json_response(status_code: int, payload: Any) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
            "access-control-allow-origin": "*",
        },
        "body": json.dumps(payload, default=_json_default),
    }


def error_response(exc: ApiError) -> dict[str, Any]:
    body: dict[str, Any] = {"error": exc.message}
    if exc.code:
        body["code"] = exc.code
    return json_response(exc.status_code, body)


INTERNAL_KEYS = frozenset({"pk", "sk", "gsi1pk", "gsi1sk"})


def public_item(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in INTERNAL_KEYS}
