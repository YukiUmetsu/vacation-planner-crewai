"""Drop places already on the trip — by place_key, name, or Google place_id."""

from __future__ import annotations

import re
from typing import Any

from db.place_keys import make_place_key, normalize_place_text


def ensure_place_key(place: dict[str, Any]) -> str:
    """Return a stable key; rewrite bare crew slugs to name|address when possible."""
    provided = str(place.get("place_key") or "").strip()
    name = str(place.get("name") or "")
    address = place.get("address")
    canonical = make_place_key(name, address)
    # Crews sometimes emit slug-only keys (``nijo_castle``) that never match
    # visited ``nijo castle|kyoto``. Prefer the canonical form when we can.
    if not provided:
        return canonical
    if "|" not in provided and canonical and canonical != "|":
        return canonical
    return provided


def _name_variants(name: str) -> set[str]:
    """Normalized name plus compact/slug forms for cross-format matching."""
    n = normalize_place_text(name)
    if not n:
        return set()
    out = {n, n.replace(" ", "_"), n.replace(" ", "-")}
    compact = re.sub(r"[^a-z0-9]+", "", n)
    if compact:
        out.add(compact)
    return {t for t in out if t}


def _name_token(place: dict[str, Any]) -> str:
    name = normalize_place_text(str(place.get("name") or ""))
    if name:
        return name
    key = str(place.get("place_key") or "").strip()
    if not key:
        return ""
    return key.split("|", 1)[0].strip()


def _usable_google_place_id(place: dict[str, Any]) -> str | None:
    """Keep in sync with places.client.is_usable_google_place_id (no places import)."""
    raw = str(place.get("place_id") or "").strip()
    if raw.startswith("places/"):
        raw = raw[len("places/") :]
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", raw):
        return None
    key = str(place.get("place_key") or "").strip()
    if key and raw == key:
        return None
    if raw.isdigit():
        return None
    if raw == raw.lower() and not raw.startswith("ChIJ"):
        if "-" in raw or "_" in raw:
            return None
    return raw


def _google_id_token(place: dict[str, Any]) -> str | None:
    normalized = _usable_google_place_id(place)
    return f"id:{normalized}" if normalized else None


def place_identity_tokens(place: dict[str, Any]) -> set[str]:
    """Identity tokens used to recognize the same venue across key formats."""
    tokens: set[str] = set()
    key = ensure_place_key(place)
    if key:
        tokens.add(key)
        tokens |= _name_variants(key.split("|", 1)[0])
    tokens |= _name_variants(_name_token(place))
    canonical = make_place_key(str(place.get("name") or ""), place.get("address"))
    if canonical and canonical != "|":
        tokens.add(canonical)
        tokens |= _name_variants(canonical.split("|", 1)[0])
    google_id = _google_id_token(place)
    if google_id:
        tokens.add(google_id)
    return {t for t in tokens if t}


def visited_identity_tokens(visited: list[str]) -> set[str]:
    """Expand stored visited keys into exact + name/slug tokens."""
    out: set[str] = set()
    for raw in visited:
        key = str(raw or "").strip()
        if not key:
            continue
        out.add(key)
        out |= _name_variants(key.split("|", 1)[0])
    return out


def places_identity_overlap(place: dict[str, Any], blocked: set[str]) -> bool:
    """True when ``place`` collides with any token in ``blocked``."""
    if not blocked:
        return False
    return bool(place_identity_tokens(place) & blocked)


def dedupe_places(
    places: list[dict[str, Any]], visited: list[str]
) -> list[dict[str, Any]]:
    """Return places not already visited; fills/canonicalizes place_key.

    Matches exact keys and normalized names so ``nijo_castle`` and
    ``nijo castle|kyoto`` count as the same venue. After Places enrich,
    Google ``place_id`` tokens also collide.
    """
    blocked = visited_identity_tokens(visited)
    out: list[dict[str, Any]] = []
    for place in places:
        if places_identity_overlap(place, blocked):
            continue
        key = ensure_place_key(place)
        enriched = {**place, "place_key": key}
        blocked |= place_identity_tokens(enriched)
        out.append(enriched)
    return out
