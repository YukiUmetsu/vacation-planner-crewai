"""Per-user GenAI action caps (hour + day) with Dynamo counters."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from db.protocols import DynamoDBTable
from http_utils import ApiError
from limits.admin import is_admin

logger = logging.getLogger(__name__)


def genai_quota_enabled() -> bool:
    flag = os.getenv("GENAI_QUOTA", "on").strip().lower()
    return flag not in {"off", "0", "false", "no"}


def _env_cap(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def hour_cap() -> int:
    return _env_cap("GENAI_CAP_HOUR", 20)


def day_cap() -> int:
    return _env_cap("GENAI_CAP_DAY", 100)


def consume_genai_action(
    *,
    user_sub: str,
    profile: dict[str, Any] | None = None,
    email: str | None = None,
    table: DynamoDBTable | None = None,
) -> None:
    """Increment hour+day counters or raise 429. No-op for admin / fake / disabled."""
    if not genai_quota_enabled():
        return
    if is_admin(profile=profile, user_sub=user_sub, email=email):
        return
    from crews.runner import crew_mode

    if crew_mode() == "fake":
        return

    from db.repository import usage as usage_repo

    now = datetime.now(timezone.utc)
    try:
        usage_repo.try_consume_genai_windows(
            user_sub=user_sub,
            now=now,
            hour_cap=hour_cap(),
            day_cap=day_cap(),
            table=table,
        )
    except usage_repo.QuotaExceeded as exc:
        raise ApiError(
            429,
            f"GenAI usage limit reached ({exc.window}). Try again later.",
            code="genai_quota_exceeded",
        ) from exc
