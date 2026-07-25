"""Traveler profile persistence."""

from __future__ import annotations

from typing import Any

from db import keys
from db.dynamo_sanitize import prepare_dynamo_item
from db.protocols import DynamoDBTable
from db.repository.common import DynamoItem, now_iso, resolve_table
from limits.admin import normalize_plan, normalize_role


def get_profile(*, user_sub: str, table: DynamoDBTable | None = None) -> DynamoItem | None:
    tbl = resolve_table(table)
    resp = tbl.get_item(Key={"pk": keys.user_pk(user_sub), "sk": keys.profile_sk()})
    item = resp.get("Item")
    return item if isinstance(item, dict) else None


def put_profile(
    *,
    user_sub: str,
    display_name: str = "",
    preferences: str = "",
    energy_level: int = 3,
    interests: list[str] | None = None,
    visited_places: list[dict[str, Any]] | None = None,
    suggest_include_breakfast: bool = False,
    role: str | None = None,
    plan: str | None = None,
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    """Write traveler fields; preserve existing role/plan unless explicitly passed."""
    tbl = resolve_table(table)
    now = now_iso()
    existing = get_profile(user_sub=user_sub, table=tbl)
    created_at = str(existing.get("created_at") or now) if existing else now
    next_role = normalize_role(
        role if role is not None else (existing.get("role") if existing else "user")
    )
    next_plan = normalize_plan(
        plan if plan is not None else (existing.get("plan") if existing else "free")
    )
    item: DynamoItem = {
        "pk": keys.user_pk(user_sub),
        "sk": keys.profile_sk(),
        "entity_type": "PROFILE",
        "user_id": user_sub,
        "display_name": display_name,
        "preferences": preferences,
        "energy_level": int(energy_level),
        "interests": list(interests or []),
        "visited_places": list(visited_places or []),
        "suggest_include_breakfast": bool(suggest_include_breakfast),
        "role": next_role,
        "plan": next_plan,
        "created_at": created_at,
        "updated_at": now,
    }
    cleaned = prepare_dynamo_item(item)
    tbl.put_item(Item=cleaned)
    return cleaned


def promote_profile_admin(*, user_sub: str, table: DynamoDBTable | None = None) -> DynamoItem:
    """Set role=admin, creating a minimal PROFILE if missing."""
    tbl = resolve_table(table)
    existing = get_profile(user_sub=user_sub, table=tbl)
    if existing and normalize_role(existing.get("role")) == "admin":
        return existing
    if existing:
        return put_profile(
            user_sub=user_sub,
            display_name=str(existing.get("display_name") or ""),
            preferences=str(existing.get("preferences") or ""),
            energy_level=int(existing.get("energy_level") or 3),
            interests=list(existing.get("interests") or []),
            visited_places=list(existing.get("visited_places") or []),
            suggest_include_breakfast=bool(existing.get("suggest_include_breakfast")),
            role="admin",
            plan=normalize_plan(existing.get("plan")),
            table=tbl,
        )
    return put_profile(user_sub=user_sub, role="admin", plan="free", table=tbl)
