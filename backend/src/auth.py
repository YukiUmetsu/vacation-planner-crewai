"""Auth: Cognito via API Gateway JWT claims (default) or local dev bypass."""

from __future__ import annotations

import os
from typing import Any

from http_utils import ApiError, normalize_headers


def auth_mode() -> str:
    # Fail closed: production must not accidentally run with forgeable identity.
    return os.getenv("AUTH_MODE", "cognito").strip().lower() or "cognito"


def _claims_from_event(event: dict[str, Any]) -> dict[str, Any]:
    """HTTP API JWT authorizer puts verified claims under requestContext.authorizer.jwt."""
    authorizer = (event.get("requestContext") or {}).get("authorizer") or {}
    jwt = authorizer.get("jwt") or {}
    claims = jwt.get("claims")
    if isinstance(claims, dict):
        return claims
    # Some payload shapes nest differently
    if isinstance(authorizer.get("claims"), dict):
        return authorizer["claims"]
    return {}


def get_user_sub(event: dict[str, Any]) -> str:
    mode = auth_mode()
    headers = normalize_headers(event)

    if mode == "dev":
        if headers.get("x-dev-user-sub"):
            return headers["x-dev-user-sub"].strip()
        env_sub = os.getenv("DEV_USER_SUB", "").strip()
        if env_sub:
            return env_sub
        return "local-dev-user"

    if mode == "cognito":
        claims = _claims_from_event(event)
        sub = claims.get("sub")
        if sub:
            return str(sub).strip()
        raise ApiError(
            401,
            "missing Cognito sub (expected API Gateway JWT authorizer claims)",
            code="unauthorized",
        )

    raise ApiError(500, f"Unknown AUTH_MODE={mode!r}", code="auth_misconfigured")
