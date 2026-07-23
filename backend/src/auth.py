"""Auth: Cognito via API Gateway JWT claims (default) or local dev bypass."""

from __future__ import annotations

import logging
import os
from contextvars import Token
from typing import Any

from crews.runner import (
    DEV_CREW_MODE_OVERRIDE_VALUES,
    reset_crew_mode_override,
    set_crew_mode_override,
)
from http_utils import ApiError, normalize_headers

logger = logging.getLogger(__name__)


def auth_mode() -> str:
    # Fail closed: production must not accidentally run with forgeable identity.
    return os.getenv("AUTH_MODE", "cognito").strip().lower() or "cognito"


def apply_dev_crew_mode_override(event: dict[str, Any]) -> Token[str | None]:
    """
    Honor ``X-Crew-Mode`` only when ``AUTH_MODE=dev``.

    Cognito / deployed Lambda ignore the header so clients cannot force AgentCore
    off (or onto a different runner) in production.
    """
    if auth_mode() != "dev":
        return set_crew_mode_override(None)
    raw = (normalize_headers(event).get("x-crew-mode") or "").strip().lower()
    if raw in DEV_CREW_MODE_OVERRIDE_VALUES:
        logger.info("dev crew_mode override=%s", raw)
        return set_crew_mode_override(raw)
    return set_crew_mode_override(None)


def clear_dev_crew_mode_override(token: Token[str | None]) -> None:
    reset_crew_mode_override(token)


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
