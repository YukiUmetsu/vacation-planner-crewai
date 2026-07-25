"""Public landmark image fallback when Google Place Photos is empty.

Uses the Wikipedia REST summary API (no API key). Good coverage for famous
venues; soft-fails for obscure / neighborhood-only stops.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from places.client import PlacesTransientError, raise_if_http_transient

logger = logging.getLogger(__name__)

_WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_WIKI_SEARCH = "https://en.wikipedia.org/w/api.php"
_UA = "VacationPlanner/1.0 (place photo fallback; local-dev)"
_TIMEOUT_SEC = 6.0
# Panel thumbs are small; allow room for a Wikipedia “original” when no thumb.
_MAX_BYTES = 900_000
# Cap title guesses so one obscure venue cannot burn the shared rate limit.
_MAX_SUMMARY_ATTEMPTS = 3
_MAX_SEARCH_ATTEMPTS = 1

# Process-local backoff after Wikipedia 429/5xx (separate from Google Places).
_WIKI_BACKOFF_UNTIL = 0.0
_WIKI_BACKOFF_SEC = 90.0


def wikipedia_lookup_in_backoff() -> bool:
    return time.monotonic() < _WIKI_BACKOFF_UNTIL


def note_wikipedia_transient(*, seconds: float | None = None) -> None:
    global _WIKI_BACKOFF_UNTIL
    _WIKI_BACKOFF_UNTIL = time.monotonic() + (
        _WIKI_BACKOFF_SEC if seconds is None else max(5.0, float(seconds))
    )


def clear_wikipedia_backoff_for_tests() -> None:
    global _WIKI_BACKOFF_UNTIL
    _WIKI_BACKOFF_UNTIL = 0.0


def _raise_if_wiki_backoff() -> None:
    if wikipedia_lookup_in_backoff():
        raise PlacesTransientError(
            "wikipedia temporarily unavailable (backoff)",
            status=429,
        )


def _http_get_json(url: str) -> dict[str, Any] | None:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": _UA, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            raise_if_http_transient(exc, what="wikipedia")
        except PlacesTransientError:
            note_wikipedia_transient()
            raise
        logger.info("wikipedia request failed: %s", exc)
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise_if_http_transient(exc, what="wikipedia")
        logger.info("wikipedia request failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.info("wikipedia unexpected error: %s", exc)
        return None
    return payload if isinstance(payload, dict) else None


def _http_get_bytes(url: str) -> tuple[bytes, str] | None:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": _UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
            data = resp.read()
            if not data:
                return None
            content_type = (
                str(resp.headers.get("Content-Type") or "").split(";")[0].strip()
                or "image/jpeg"
            )
            if not content_type.startswith("image/"):
                return None
            return data, content_type
    except urllib.error.HTTPError as exc:
        try:
            raise_if_http_transient(exc, what="wikipedia image")
        except PlacesTransientError:
            note_wikipedia_transient()
            raise
        logger.info("wikipedia image fetch failed: %s", exc)
        return None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise_if_http_transient(exc, what="wikipedia image")
        logger.info("wikipedia image fetch failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.info("wikipedia image unexpected error: %s", exc)
        return None


def _candidate_titles(name: str, city: str) -> list[str]:
    """Build Wikipedia title guesses from a crew place name + overnight city."""
    raw = re.sub(r"\s+", " ", (name or "").strip())
    if not raw:
        return []
    city = re.sub(r"\s+", " ", (city or "").strip())
    # Drop filler words that hurt Wikipedia title match.
    cleaned = re.sub(
        r"\b(and|the|a|an)\b",
        " ",
        raw,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    out: list[str] = []
    for title in (
        raw,
        cleaned,
        f"{raw} ({city})" if city else "",
        f"{cleaned} ({city})" if city and cleaned != raw else "",
        f"{cleaned}, {city}" if city and cleaned else "",
    ):
        t = title.strip()
        if t and t not in out:
            out.append(t)
    return out


def _summary_image_url(title: str) -> str | None:
    encoded = urllib.parse.quote(title.replace(" ", "_"), safe="")
    payload = _http_get_json(_WIKI_SUMMARY.format(title=encoded))
    if not payload or payload.get("type") == "disambiguation":
        return None
    # Prefer thumbnail — originals are often multi‑MB and blow the data-URL budget.
    for key in ("thumbnail", "originalimage"):
        block = payload.get(key)
        if isinstance(block, dict):
            src = str(block.get("source") or "").strip()
            if src.startswith("http"):
                return src
    return None


def _search_title(query: str) -> str | None:
    qs = urllib.parse.urlencode(
        {
            "action": "opensearch",
            "search": query,
            "limit": "1",
            "namespace": "0",
            "format": "json",
        }
    )
    # opensearch returns a list, not an object — use raw fetch.
    req = urllib.request.Request(
        f"{_WIKI_SEARCH}?{qs}",
        method="GET",
        headers={"User-Agent": _UA, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            raise_if_http_transient(exc, what="wikipedia search")
        except PlacesTransientError:
            note_wikipedia_transient()
            raise
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise_if_http_transient(exc, what="wikipedia search")
        return None
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, list) or len(payload) < 2:
        return None
    titles = payload[1]
    if isinstance(titles, list) and titles:
        hit = str(titles[0] or "").strip()
        return hit or None
    return None


def lookup_wikipedia_image_url(name: str, *, city: str = "") -> str | None:
    """Return a Wikimedia image URL for a place name, or None."""
    _raise_if_wiki_backoff()
    titles = _candidate_titles(name, city)
    for title in titles[:_MAX_SUMMARY_ATTEMPTS]:
        url = _summary_image_url(title)
        if url:
            return url
    # OpenSearch when direct title guesses miss (e.g. "Meiji Shrine" → "Meiji Jingū").
    for query in titles[:_MAX_SEARCH_ATTEMPTS]:
        found = _search_title(query)
        if found:
            url = _summary_image_url(found)
            if url:
                return url
    return None


def resolve_wikipedia_photo_payload(
    name: str,
    *,
    city: str = "",
    include_bytes: bool = True,
) -> dict[str, str | None]:
    """Build the same shape as Places photo resolve, using Wikipedia imagery."""
    empty: dict[str, str | None] = {
        "photo_url": None,
        "places_photo_name": None,
        "photo_data_url": None,
    }
    url = lookup_wikipedia_image_url(name, city=city)
    if not url:
        return empty

    if not include_bytes or wikipedia_lookup_in_backoff():
        return {
            "photo_url": url,
            "places_photo_name": None,
            "photo_data_url": None,
        }

    fetched = _http_get_bytes(url)
    if fetched is None:
        return {
            "photo_url": url,
            "places_photo_name": None,
            "photo_data_url": None,
        }
    data, content_type = fetched
    photo_data_url: str | None = None
    if len(data) <= _MAX_BYTES:
        b64 = base64.b64encode(data).decode("ascii")
        photo_data_url = f"data:{content_type};base64,{b64}"
    return {
        "photo_url": url,
        "places_photo_name": None,
        "photo_data_url": photo_data_url,
    }


def resolve_cached_stable_photo_payload(
    photo_url: str,
    *,
    places_photo_name: str | None = None,
    include_bytes: bool = True,
) -> dict[str, str | None]:
    """Rebuild a photo payload from a previously persisted stable URL."""
    empty: dict[str, str | None] = {
        "photo_url": None,
        "places_photo_name": places_photo_name,
        "photo_data_url": None,
    }
    url = str(photo_url or "").strip()
    if not url.startswith("http"):
        return empty
    out: dict[str, str | None] = {
        "photo_url": url,
        "places_photo_name": places_photo_name,
        "photo_data_url": None,
    }
    # Skip byte fetch while Wikimedia is rate-limiting.
    if not include_bytes or wikipedia_lookup_in_backoff():
        return out
    fetched = _http_get_bytes(url)
    if fetched is None:
        return out
    data, content_type = fetched
    if len(data) <= _MAX_BYTES:
        b64 = base64.b64encode(data).decode("ascii")
        out["photo_data_url"] = f"data:{content_type};base64,{b64}"
    return out
