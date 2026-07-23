"""API Gateway request/response helpers."""

from __future__ import annotations

import base64
import json
import os
import re
from decimal import Decimal
from typing import Any


_TRIP_ID_RE = re.compile(
    r"^/trips(?:/(?P<trip_id>[^/]+))?(?:/(?P<action>propose-cities|cities|plan-next-day))?/?$"
)
_DAY_ACTION_RE = re.compile(
    r"^/trips/(?P<trip_id>[^/]+)/days/(?P<day_index>\d+)/(?P<action>suggest-place)/?$"
)
_DAY_RESOURCE_RE = re.compile(
    r"^/trips/(?P<trip_id>[^/]+)/days/(?P<day_index>\d+)/?$"
)
_DAY_PLACE_RE = re.compile(
    r"^/trips/(?P<trip_id>[^/]+)/days/(?P<day_index>\d+)/places/(?P<place_index>\d+)/?$"
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


# Codes whose ``message`` may contain SDK / filesystem / stack detail — never echo to clients.
_PUBLIC_BY_CODE: dict[str, str] = {
    "crew_failed": "Trip planning failed. Please try again.",
    "crew_not_found": "Trip planning failed. Please try again.",
    "agent_invoke_failed": "Trip planning is temporarily unavailable. Please try again.",
    "agent_auth_failed": (
        "AgentCore rejected local AWS credentials. "
        "Restart ./scripts/dev.sh with a valid AWS profile "
        "(unset AWS_ACCESS_KEY_ID=local if set)."
    ),
    "agent_bad_response": "Trip planning failed. Please try again.",
    "agent_misconfigured": "Trip planning is temporarily unavailable. Please try again.",
    "agent_error": "Trip planning failed. Please try again.",
    "internal_error": "Something went wrong. Please try again.",
    "persistence_error": "Could not save your trip. Please try again.",
    "enqueue_failed": "Trip planning is temporarily unavailable. Please try again.",
}

_DEFAULT_5XX = "Something went wrong. Please try again."


def client_facing_message(
    *,
    status_code: int,
    code: str | None,
    detail: str,
) -> str:
    """Safe string for HTTP JSON / ``planning_error``; keep ``detail`` for logs only when replaced."""
    if code and code in _PUBLIC_BY_CODE:
        return _PUBLIC_BY_CODE[code]
    if status_code >= 500:
        return _DEFAULT_5XX
    return detail


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


def parse_day_resource(path: str) -> tuple[str, int] | None:
    """Return (trip_id, day_index) for /trips/{id}/days/{n}."""
    match = _DAY_RESOURCE_RE.match(path)
    if not match:
        return None
    return match.group("trip_id"), int(match.group("day_index"))


def parse_day_place(path: str) -> tuple[str, int, int] | None:
    """Return (trip_id, day_index, place_index) for /trips/{id}/days/{n}/places/{i}."""
    match = _DAY_PLACE_RE.match(path)
    if not match:
        return None
    return (
        match.group("trip_id"),
        int(match.group("day_index")),
        int(match.group("place_index")),
    )


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
    headers: dict[str, str] = {
        "content-type": "application/json",
        "access-control-allow-origin": "*",
        "access-control-allow-headers": (
            "authorization,content-type,x-requested-with,"
            "x-dev-user-sub,x-crew-mode"
        ),
        "access-control-allow-methods": "GET,POST,PUT,DELETE,OPTIONS",
    }
    # Local DEV only: let the browser Network tab prove which runner handled the request.
    if os.getenv("AUTH_MODE", "").strip().lower() == "dev":
        from crews.runner import crew_mode

        headers["x-crew-mode-effective"] = crew_mode()
        headers["access-control-expose-headers"] = "x-crew-mode-effective"
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(payload, default=_json_default),
    }


def error_response(exc: ApiError) -> dict[str, Any]:
    body: dict[str, Any] = {
        "error": client_facing_message(
            status_code=exc.status_code,
            code=exc.code,
            detail=exc.message,
        )
    }
    if exc.code:
        body["code"] = exc.code
    return json_response(exc.status_code, body)


INTERNAL_KEYS = frozenset({"pk", "sk", "gsi1pk", "gsi1sk"})


def public_item(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in INTERNAL_KEYS}
