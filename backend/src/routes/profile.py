"""Profile HTTP routes."""

from __future__ import annotations

from typing import Any

from auth import get_user_email
from db.protocols import DynamoDBTable
from http_utils import parse_body
from safety.gate import SafetyGate
from user_profile.service import ProfileService


def _service(
    *,
    table: DynamoDBTable | None = None,
    safety: SafetyGate | None = None,
) -> ProfileService:
    return ProfileService(table=table, safety=safety)


def get_profile(event: dict[str, Any], user_sub: str, **kwargs: Any) -> dict[str, Any]:
    return {
        "profile": _service(**kwargs).get_profile(
            user_sub, email=get_user_email(event)
        )
    }


def put_profile(event: dict[str, Any], user_sub: str, **kwargs: Any) -> dict[str, Any]:
    return {
        "profile": _service(**kwargs).put_profile(
            user_sub, parse_body(event), email=get_user_email(event)
        )
    }
