"""Admin checks: PROFILE role is source of truth; env bootstraps promote."""

from __future__ import annotations

import os
from typing import Any


def admin_emails() -> set[str]:
    raw = os.getenv("ADMIN_EMAILS", "").strip()
    if not raw:
        return set()
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def metrics_admin_subs() -> set[str]:
    """Break-glass Cognito/dev subs (also used historically for /admin/metrics)."""
    raw = os.getenv("METRICS_ADMIN_SUBS", "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def normalize_role(value: Any) -> str:
    role = str(value or "user").strip().lower()
    return "admin" if role == "admin" else "user"


def normalize_plan(value: Any) -> str:
    plan = str(value or "free").strip().lower()
    return plan or "free"


def is_admin(
    *,
    profile: dict[str, Any] | None = None,
    user_sub: str = "",
    email: str | None = None,
) -> bool:
    """True when PROFILE role is admin, or break-glass sub/email allowlists match."""
    if profile and normalize_role(profile.get("role")) == "admin":
        return True
    sub = (user_sub or "").strip()
    if sub and sub in metrics_admin_subs():
        return True
    mail = (email or "").strip().lower()
    if mail and mail in admin_emails():
        return True
    return False
