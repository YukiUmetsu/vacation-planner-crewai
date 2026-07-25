"""User limits: admin role, trip caps, GenAI action caps (ADR 006)."""

from limits.admin import admin_emails, is_admin, metrics_admin_subs, normalize_plan, normalize_role
from limits.genai import consume_genai_action, genai_quota_enabled, refund_genai_action
from limits.trips import assert_can_create_trip, max_trips_for_user

__all__ = [
    "admin_emails",
    "assert_can_create_trip",
    "consume_genai_action",
    "refund_genai_action",
    "genai_quota_enabled",
    "is_admin",
    "max_trips_for_user",
    "metrics_admin_subs",
    "normalize_plan",
    "normalize_role",
]
