"""Single-table key helpers — see docs/DATA_MODEL.md."""

from __future__ import annotations


def user_pk(sub: str) -> str:
    return f"USER#{sub}"


def trip_sk(trip_id: str) -> str:
    return f"TRIP#{trip_id}"


def route_sk(trip_id: str) -> str:
    return f"TRIP#{trip_id}#ROUTE"


def day_sk(trip_id: str, day_index: int) -> str:
    return f"TRIP#{trip_id}#DAY#{day_index:02d}"


def gsi1_pk(trip_id: str) -> str:
    return f"TRIP#{trip_id}"


def gsi1_sk_user(sub: str) -> str:
    return f"USER#{sub}"


def gsi1_sk_route() -> str:
    return "ROUTE"


def gsi1_sk_day(day_index: int) -> str:
    return f"DAY#{day_index:02d}"


def profile_sk() -> str:
    """User profile meta — not under TRIP# so list_trips ignores it."""
    return "PROFILE"
