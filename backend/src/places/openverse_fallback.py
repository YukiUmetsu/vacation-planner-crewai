"""Openverse CC image fallback when Google / Wikipedia / Wikidata miss."""

from __future__ import annotations

import logging
import re
import time
import urllib.parse

from places.client import PlacesTransientError
from places.image_http import (
    empty_photo_payload,
    http_get_json,
    payload_from_image_url,
)

logger = logging.getLogger(__name__)

_OPENVERSE_IMAGES = "https://api.openverse.org/v1/images/"

_BACKOFF_UNTIL = 0.0
_BACKOFF_SEC = 90.0


def openverse_lookup_in_backoff() -> bool:
    return time.monotonic() < _BACKOFF_UNTIL


def note_openverse_transient(*, seconds: float | None = None) -> None:
    global _BACKOFF_UNTIL
    _BACKOFF_UNTIL = time.monotonic() + (
        _BACKOFF_SEC if seconds is None else max(5.0, float(seconds))
    )


def clear_openverse_backoff_for_tests() -> None:
    global _BACKOFF_UNTIL
    _BACKOFF_UNTIL = 0.0


def _raise_if_backoff() -> None:
    if openverse_lookup_in_backoff():
        raise PlacesTransientError(
            "openverse temporarily unavailable (backoff)",
            status=429,
        )


def lookup_openverse_image_url(name: str, *, city: str = "") -> str | None:
    """Return a CC image URL from Openverse, preferring the API thumbnail."""
    _raise_if_backoff()
    raw = re.sub(r"\s+", " ", (name or "").strip())
    if not raw:
        return None
    city = re.sub(r"\s+", " ", (city or "").strip())
    query = f"{raw} {city}".strip() if city else raw
    qs = urllib.parse.urlencode(
        {
            "q": query,
            "page_size": "1",
            # Stay on redistributable licenses.
            "license": "cc0,by,by-sa,by-nc,by-nd,by-nc-sa,by-nc-nd,pdm",
        }
    )
    payload = http_get_json(
        f"{_OPENVERSE_IMAGES}?{qs}",
        what="openverse",
        on_transient=note_openverse_transient,
    )
    if not payload:
        return None
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return None
    hit = results[0]
    if not isinstance(hit, dict):
        return None
    # Prefer Openverse-hosted thumb (smaller, stable path) over foreign CDN.
    for key in ("thumbnail", "url"):
        src = str(hit.get(key) or "").strip()
        if src.startswith("http"):
            return src
    return None


def resolve_openverse_photo_payload(
    name: str,
    *,
    city: str = "",
    include_bytes: bool = True,
) -> dict[str, str | None]:
    """Build the Places photo payload shape using Openverse search."""
    url = lookup_openverse_image_url(name, city=city)
    if not url:
        return empty_photo_payload()
    return payload_from_image_url(
        url,
        include_bytes=include_bytes,
        what="openverse image",
        on_transient=note_openverse_transient,
        skip_bytes=openverse_lookup_in_backoff(),
    )
