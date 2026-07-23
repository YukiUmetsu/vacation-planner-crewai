"""Profile HTTP routes."""

from __future__ import annotations

from typing import Any

from db.protocols import DynamoDBTable
from http_utils import parse_body
from services.profile_service import ProfileService
from services.safety import SafetyGate


def _service(
    *,
    table: DynamoDBTable | None = None,
    safety: SafetyGate | None = None,
) -> ProfileService:
    return ProfileService(table=table, safety=safety)


def get_profile(event: dict[str, Any], user_sub: str, **kwargs: Any) -> dict[str, Any]:
    # Missing profiles return defaults with persisted=false (no 404 noise).
    return {"profile": _service(**kwargs).get_profile(user_sub)}


def put_profile(event: dict[str, Any], user_sub: str, **kwargs: Any) -> dict[str, Any]:
    return {"profile": _service(**kwargs).put_profile(user_sub, parse_body(event))}
