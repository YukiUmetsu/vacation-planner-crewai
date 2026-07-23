"""Traveler profile persistence."""

from __future__ import annotations

from typing import Any

from db import keys
from db.dynamo_sanitize import prepare_dynamo_item
from db.protocols import DynamoDBTable
from db.repository.common import DynamoItem, now_iso, resolve_table


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
    table: DynamoDBTable | None = None,
) -> DynamoItem:
    tbl = resolve_table(table)
    now = now_iso()
    existing = get_profile(user_sub=user_sub, table=tbl)
    created_at = str(existing.get("created_at") or now) if existing else now
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
        "created_at": created_at,
        "updated_at": now,
    }
    cleaned = prepare_dynamo_item(item)
    tbl.put_item(Item=cleaned)
    return cleaned
