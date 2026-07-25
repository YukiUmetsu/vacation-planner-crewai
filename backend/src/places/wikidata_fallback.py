"""Wikidata P18 (image) fallback when Wikipedia page summary has no photo."""

from __future__ import annotations

import logging
import re
import time
import urllib.parse
from typing import Any

from places.client import PlacesTransientError
from places.image_http import (
    empty_photo_payload,
    http_get_json,
    payload_from_image_url,
)

logger = logging.getLogger(__name__)

_WD_API = "https://www.wikidata.org/w/api.php"
_COMMONS_FILE = "https://commons.wikimedia.org/wiki/Special:FilePath/{file}"

_BACKOFF_UNTIL = 0.0
_BACKOFF_SEC = 90.0


def wikidata_lookup_in_backoff() -> bool:
    return time.monotonic() < _BACKOFF_UNTIL


def note_wikidata_transient(*, seconds: float | None = None) -> None:
    global _BACKOFF_UNTIL
    _BACKOFF_UNTIL = time.monotonic() + (
        _BACKOFF_SEC if seconds is None else max(5.0, float(seconds))
    )


def clear_wikidata_backoff_for_tests() -> None:
    global _BACKOFF_UNTIL
    _BACKOFF_UNTIL = 0.0


def _raise_if_backoff() -> None:
    if wikidata_lookup_in_backoff():
        raise PlacesTransientError(
            "wikidata temporarily unavailable (backoff)",
            status=429,
        )


def _search_entity_id(name: str, city: str) -> str | None:
    queries = []
    raw = re.sub(r"\s+", " ", (name or "").strip())
    city = re.sub(r"\s+", " ", (city or "").strip())
    if not raw:
        return None
    if city:
        queries.append(f"{raw} {city}")
    queries.append(raw)
    city_l = city.lower()
    for query in queries:
        qs = urllib.parse.urlencode(
            {
                "action": "wbsearchentities",
                "search": query,
                "language": "en",
                "limit": "5",
                "format": "json",
            }
        )
        payload = http_get_json(
            f"{_WD_API}?{qs}",
            what="wikidata search",
            on_transient=note_wikidata_transient,
        )
        if not payload:
            continue
        hits = payload.get("search")
        if not isinstance(hits, list) or not hits:
            continue
        # Prefer a hit whose label/description mentions the city.
        ranked: list[dict[str, Any]] = [
            h for h in hits if isinstance(h, dict) and h.get("id")
        ]
        if city_l:
            for hit in ranked:
                blob = " ".join(
                    [
                        str(hit.get("label") or ""),
                        str(hit.get("description") or ""),
                    ]
                ).lower()
                if city_l in blob:
                    return str(hit["id"])
        return str(ranked[0]["id"])
    return None


def _p18_filename(entity_id: str) -> str | None:
    qs = urllib.parse.urlencode(
        {
            "action": "wbgetentities",
            "ids": entity_id,
            "props": "claims",
            "format": "json",
        }
    )
    payload = http_get_json(
        f"{_WD_API}?{qs}",
        what="wikidata entity",
        on_transient=note_wikidata_transient,
    )
    if not payload:
        return None
    entities = payload.get("entities")
    if not isinstance(entities, dict):
        return None
    entity = entities.get(entity_id)
    if not isinstance(entity, dict):
        return None
    claims = entity.get("claims")
    if not isinstance(claims, dict):
        return None
    p18 = claims.get("P18")
    if not isinstance(p18, list) or not p18:
        return None
    first = p18[0]
    if not isinstance(first, dict):
        return None
    mainsnak = first.get("mainsnak")
    if not isinstance(mainsnak, dict):
        return None
    datavalue = mainsnak.get("datavalue")
    if not isinstance(datavalue, dict):
        return None
    value = str(datavalue.get("value") or "").strip()
    return value or None


def commons_thumb_url(filename: str, *, width: int = 640) -> str:
    """Build a Commons Special:FilePath URL (redirects to upload.wikimedia.org)."""
    encoded = urllib.parse.quote(filename.replace(" ", "_"), safe="")
    return f"{_COMMONS_FILE.format(file=encoded)}?width={int(width)}"


def lookup_wikidata_image_url(name: str, *, city: str = "") -> str | None:
    """Return a Commons image URL from Wikidata P18, or None."""
    _raise_if_backoff()
    entity_id = _search_entity_id(name, city)
    if not entity_id:
        return None
    filename = _p18_filename(entity_id)
    if not filename:
        logger.info("wikidata P18 missing entity=%s name=%r", entity_id, name)
        return None
    return commons_thumb_url(filename)


def resolve_wikidata_photo_payload(
    name: str,
    *,
    city: str = "",
    include_bytes: bool = True,
) -> dict[str, str | None]:
    """Build the Places photo payload shape using Wikidata P18 → Commons."""
    url = lookup_wikidata_image_url(name, city=city)
    if not url:
        return empty_photo_payload()
    return payload_from_image_url(
        url,
        include_bytes=include_bytes,
        what="wikidata image",
        on_transient=note_wikidata_transient,
        skip_bytes=wikidata_lookup_in_backoff(),
    )
