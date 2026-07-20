"""Drop places whose place_key is already on the trip."""

from __future__ import annotations

from typing import Any

from db.place_keys import make_place_key


def ensure_place_key(place: dict[str, Any]) -> str:
    key = str(place.get("place_key") or "").strip()
    if key:
        return key
    return make_place_key(str(place.get("name") or ""), place.get("address"))


def dedupe_places(places: list[dict[str, Any]], visited: list[str]) -> list[dict[str, Any]]:
    """Return places not already in visited; fills place_key when missing."""
    seen = set(visited)
    out: list[dict[str, Any]] = []
    for place in places:
        key = ensure_place_key(place)
        enriched = {**place, "place_key": key}
        if key in seen:
            continue
        seen.add(key)
        out.append(enriched)
    return out
