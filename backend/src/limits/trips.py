"""Trip count limits from PROFILE plan (+ env)."""

from __future__ import annotations

import os
from typing import Any

from http_utils import ApiError
from limits.admin import is_admin, normalize_plan


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def max_trips_for_user(profile: dict[str, Any] | None, *, user_sub: str = "", email: str | None = None) -> int | None:
    """Return max trips, or None for unlimited (admin)."""
    if is_admin(profile=profile, user_sub=user_sub, email=email):
        return None
    plan = normalize_plan((profile or {}).get("plan"))
    if plan == "free":
        return _env_int("FREE_PLAN_MAX_TRIPS", 1)
    # Unknown / future paid plans: fall back to free cap until mapped.
    return _env_int("FREE_PLAN_MAX_TRIPS", 1)


def assert_can_create_trip(
    *,
    user_sub: str,
    trip_count: int,
    profile: dict[str, Any] | None,
    email: str | None = None,
) -> None:
    max_trips = max_trips_for_user(profile, user_sub=user_sub, email=email)
    if max_trips is None:
        return
    if trip_count >= max_trips:
        raise ApiError(
            403,
            "Free plan allows a limited number of trips. Delete an existing trip or upgrade later.",
            code="free_trip_limit",
        )
