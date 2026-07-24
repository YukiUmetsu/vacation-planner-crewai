"""Caching strategy for place photos.

Layers (cheapest first):

1. **DynamoDB nested keys on each place** in DAY.``places`` — durable
   ``photo_url`` (Wikimedia), ``place_id``, ``places_photo_name``,
   ``photo_status`` / ``photo_checked_at``.
2. **Short in-process cache** — ~15m URL payloads (Strict Mode + re-open).
3. **Process negative cache** — ~30m; durable miss also on the place (7d).

Never persist Google CDN ``lh3.googleusercontent.com`` URLs (they expire).
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from db import repository as repo
from db.repository.common import now_iso

logger = logging.getLogger(__name__)

_POSITIVE_TTL_SEC = 15 * 60
_NEGATIVE_TTL_SEC = 30 * 60
_MAX_POSITIVE_ENTRIES = 64

# Soft TTLs for fields nested on the place (plan).
MISS_TTL_SEC = 7 * 24 * 3600
PHOTO_NAME_TTL_SEC = 7 * 24 * 3600

_POSITIVE: OrderedDict[str, tuple[float, dict[str, str | None]]] = OrderedDict()
_NEGATIVE: dict[str, float] = {}

_STABLE_HOST_SUFFIXES = (
    "upload.wikimedia.org",
    "commons.wikimedia.org",
)


def cache_key(*, trip_id: str, place_key: str = "", name: str = "", city: str = "") -> str:
    key = (place_key or "").strip()
    if key:
        return f"trip:{trip_id.strip()}|key:{key}"
    return (
        f"trip:{trip_id.strip()}|name:{(name or '').strip().lower()}"
        f"|city:{(city or '').strip().lower()}"
    )


def lookup_key(*, name: str = "", city: str = "") -> str:
    """Cross-trip key for Wikipedia / Text Search misses (by venue identity)."""
    return f"lookup:{(name or '').strip().lower()}|{(city or '').strip().lower()}"


def get_cached_payload(key: str) -> dict[str, str | None] | None:
    hit = _POSITIVE.get(key)
    if not hit:
        return None
    expires, payload = hit
    if time.monotonic() > expires:
        _POSITIVE.pop(key, None)
        return None
    _POSITIVE.move_to_end(key)
    return dict(payload)


def set_cached_payload(key: str, payload: dict[str, str | None]) -> None:
    if not payload.get("photo_data_url") and not payload.get("photo_url"):
        return
    slim = dict(payload)
    if slim.get("photo_url") and is_stable_photo_url(slim.get("photo_url")):
        slim["photo_data_url"] = None
    _POSITIVE[key] = (time.monotonic() + _POSITIVE_TTL_SEC, slim)
    _POSITIVE.move_to_end(key)
    while len(_POSITIVE) > _MAX_POSITIVE_ENTRIES:
        _POSITIVE.popitem(last=False)
    _NEGATIVE.pop(key, None)


def is_negative_cached(key: str) -> bool:
    expires = _NEGATIVE.get(key)
    if expires is None:
        return False
    if time.monotonic() > expires:
        _NEGATIVE.pop(key, None)
        return False
    return True


def set_negative_cached(*keys: str) -> None:
    expires = time.monotonic() + _NEGATIVE_TTL_SEC
    for key in keys:
        if key:
            _NEGATIVE[key] = expires


def is_stable_photo_url(url: str | None) -> bool:
    """True when the URL is safe to reuse across sessions (not a short-lived CDN)."""
    raw = str(url or "").strip()
    if not raw.startswith("http"):
        return False
    host = (urlparse(raw).hostname or "").lower()
    return any(host == suffix or host.endswith("." + suffix) for suffix in _STABLE_HOST_SUFFIXES)


def _parse_checked_at(raw: Any) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _age_seconds(place: dict[str, Any]) -> float | None:
    checked = _parse_checked_at(place.get("photo_checked_at"))
    if checked is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - checked).total_seconds())


def is_fresh_photo_miss(place: dict[str, Any]) -> bool:
    """Durable negative cache: photo_status=none within miss TTL."""
    status = str(place.get("photo_status") or "").strip().lower()
    if status != "none":
        return False
    age = _age_seconds(place)
    if age is None:
        return True  # status set but no timestamp — treat as fresh miss
    return age < MISS_TTL_SEC


def places_photo_name_is_stale(place: dict[str, Any]) -> bool:
    """True when places_photo_name should be refreshed via Place Details."""
    name = str(place.get("places_photo_name") or "").strip()
    if not name:
        return True
    age = _age_seconds(place)
    if age is None:
        return False  # have a name, unknown age — use it once
    return age >= PHOTO_NAME_TTL_SEC


def persist_place_photo_fields(
    *,
    user_sub: str,
    trip_id: str,
    day_index: int,
    place_key: str,
    photo_url: str | None = None,
    place_id: str | None = None,
    places_photo_name: str | None = None,
    photo_status: str | None = None,
) -> None:
    """Write durable photo refs onto the DAY place (best-effort)."""
    key = (place_key or "").strip()
    if not key or day_index < 1:
        return
    try:
        day = repo.get_day(user_sub=user_sub, trip_id=trip_id, day_index=day_index)
        if not day:
            return
        places = day.get("places") or []
        if not isinstance(places, list):
            return
        updated: list[dict[str, Any]] = []
        changed = False
        checked_at = now_iso()
        status = (photo_status or "").strip().lower() or None
        for raw in places:
            if not isinstance(raw, dict):
                continue
            place = dict(raw)
            if str(place.get("place_key") or "").strip() != key:
                updated.append(place)
                continue

            if status == "none":
                # Durable miss: drop any prior URL so FE cannot short-circuit on it.
                if place.get("photo_url"):
                    place.pop("photo_url", None)
                    changed = True
                if place.get("photo_status") != "none":
                    place["photo_status"] = "none"
                    changed = True
                place["photo_checked_at"] = checked_at
                changed = True
                if place_id and place.get("place_id") != place_id:
                    place["place_id"] = place_id
                    changed = True
                updated.append(place)
                continue

            if photo_url and is_stable_photo_url(photo_url):
                if place.get("photo_url") != photo_url:
                    place["photo_url"] = photo_url
                    changed = True
            if place_id and place.get("place_id") != place_id:
                place["place_id"] = place_id
                changed = True
            if places_photo_name and place.get("places_photo_name") != places_photo_name:
                place["places_photo_name"] = places_photo_name
                changed = True
            if status == "ok" or photo_url or places_photo_name or place_id:
                if place.get("photo_status") != "ok":
                    place["photo_status"] = "ok"
                    changed = True
                place["photo_checked_at"] = checked_at
                changed = True
            updated.append(place)
        if not changed:
            return
        repo.replace_day_places(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            places=updated,
            expected_place_count=len(places),
        )
    except Exception as exc:  # noqa: BLE001 — cache write must not break photo response
        logger.info(
            "place photo persist skipped trip=%s day=%s key=%s: %s",
            trip_id,
            day_index,
            key,
            exc,
        )


def clear_cache_for_tests() -> None:
    _POSITIVE.clear()
    _NEGATIVE.clear()
