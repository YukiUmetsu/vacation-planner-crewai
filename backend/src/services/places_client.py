"""Google Places API (New) Text Search client for venue open-status."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

SEARCH_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
LEGACY_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
LEGACY_PHOTO_URL = "https://maps.googleapis.com/maps/api/place/photo"
# Photos via Text Search need Text Search Pro; pull photos from Place Details / legacy instead.
FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.businessStatus,places.regularOpeningHours,"
    "places.priceLevel,places.priceRange"
)
PLACE_DETAILS_FIELD_MASK = "id,photos"
DEFAULT_TIMEOUT_SEC = 8.0
DEFAULT_MAX_RESULTS = 5
# Google Places photo resource: places/{place_id}/photos/{photo_ref}
_PHOTO_NAME_RE = re.compile(r"^places/[^/]+/photos/[^/]+$")
_PLACE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,200}$")
_PHOTO_PAYLOAD_CACHE: dict[str, tuple[float, dict[str, str | None]]] = {}
_PHOTO_CACHE_TTL_SEC = 3600.0

_PRICE_LEVEL_LABELS: dict[str, str] = {
    "PRICE_LEVEL_FREE": "Free",
    "PRICE_LEVEL_INEXPENSIVE": "$ · Inexpensive",
    "PRICE_LEVEL_MODERATE": "$$ · Moderate",
    "PRICE_LEVEL_EXPENSIVE": "$$$ · Expensive",
    "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$ · Very expensive",
}


@dataclass(frozen=True)
class PlacesLookupResult:
    place_id: str | None
    business_status: str | None
    formatted_address: str | None
    display_name: str | None
    regular_opening_hours: dict[str, Any] | None
    price_level: str | None = None
    price_range: dict[str, Any] | None = None
    photo_name: str | None = None


class PlacesClient(Protocol):
    def search_text(
        self, text_query: str, *, max_results: int = DEFAULT_MAX_RESULTS
    ) -> list[PlacesLookupResult]: ...


def format_places_cost(
    price_level: str | None,
    price_range: dict[str, Any] | None,
) -> str | None:
    """Human cost line from Places priceRange (preferred) or priceLevel."""
    range_text = _format_price_range(price_range)
    level_text = _PRICE_LEVEL_LABELS.get((price_level or "").strip().upper())
    if range_text and level_text:
        return f"{range_text} ({level_text})"
    return range_text or level_text


def _money_amount(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    currency = str(raw.get("currencyCode") or "").strip().upper()
    try:
        units = int(raw.get("units") or 0)
    except (TypeError, ValueError):
        units = 0
    try:
        nanos = int(raw.get("nanos") or 0)
    except (TypeError, ValueError):
        nanos = 0
    # Round minor units to whole currency for display.
    if nanos >= 500_000_000:
        units += 1
    if currency in {"JPY", "KRW", "VND"}:
        amount = f"{units:,}"
    else:
        amount = f"{units:,.0f}" if nanos == 0 else f"{units + nanos / 1e9:,.2f}"
    symbols = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "KRW": "₩"}
    symbol = symbols.get(currency, f"{currency} " if currency else "")
    return f"{symbol}{amount}".strip()


def _format_price_range(price_range: dict[str, Any] | None) -> str | None:
    if not isinstance(price_range, dict):
        return None
    start = _money_amount(price_range.get("startPrice"))
    end = _money_amount(price_range.get("endPrice"))
    if start and end:
        return f"{start}–{end}"
    if start:
        return f"From {start}"
    if end:
        return f"Up to {end}"
    return None


def _first_photo_name(raw: dict[str, Any]) -> str | None:
    photos = raw.get("photos")
    if not isinstance(photos, list) or not photos:
        return None
    first = photos[0]
    if not isinstance(first, dict):
        return None
    name = str(first.get("name") or "").strip()
    return name or None


def _parse_place(raw: dict[str, Any]) -> PlacesLookupResult | None:
    if not isinstance(raw, dict):
        return None

    display = raw.get("displayName")
    display_name = None
    if isinstance(display, dict):
        display_name = str(display.get("text") or "").strip() or None
    elif isinstance(display, str) and display.strip():
        display_name = display.strip()

    place_id = str(raw["id"]).strip() if raw.get("id") else None
    if place_id and place_id.startswith("places/"):
        place_id = place_id.removeprefix("places/")

    hours = raw.get("regularOpeningHours")
    price_range = raw.get("priceRange")
    return PlacesLookupResult(
        place_id=place_id,
        business_status=str(raw["businessStatus"]).strip()
        if raw.get("businessStatus")
        else None,
        formatted_address=str(raw["formattedAddress"]).strip()
        if raw.get("formattedAddress")
        else None,
        display_name=display_name,
        regular_opening_hours=hours if isinstance(hours, dict) else None,
        price_level=str(raw["priceLevel"]).strip() if raw.get("priceLevel") else None,
        price_range=price_range if isinstance(price_range, dict) else None,
        photo_name=_first_photo_name(raw),
    )


class GooglePlacesClient:
    """POST places:searchText; returns matches or [] on soft failure."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        url: str = SEARCH_TEXT_URL,
    ) -> None:
        self._api_key = api_key.strip()
        self._timeout_sec = timeout_sec
        self._url = url

    def search_text(
        self, text_query: str, *, max_results: int = DEFAULT_MAX_RESULTS
    ) -> list[PlacesLookupResult]:
        query = text_query.strip()
        if not query or not self._api_key:
            return []
        count = max(1, min(int(max_results), 20))
        body = json.dumps({"textQuery": query, "pageSize": count}).encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self._api_key,
                "X-Goog-FieldMask": FIELD_MASK,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_sec) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning("places search_text failed: %s", exc)
            return []
        except Exception as exc:  # noqa: BLE001 — soft enrich boundary
            logger.warning("places search_text unexpected error: %s", exc)
            return []

        if not isinstance(payload, dict):
            logger.warning("places search_text non-object response for %r", query[:80])
            return []
        if payload.get("error"):
            logger.warning(
                "places search_text error for %r: %s",
                query[:80],
                str(payload.get("error"))[:300],
            )
            return []
        places = payload.get("places")
        if not isinstance(places, list) or not places:
            logger.info("places search_text empty for %r", query[:80])
            return []

        out: list[PlacesLookupResult] = []
        for item in places:
            parsed = _parse_place(item) if isinstance(item, dict) else None
            if parsed is not None:
                out.append(parsed)
        return out

    def photo_media_uri(
        self, photo_name: str, *, max_height_px: int = 640
    ) -> str | None:
        """Resolve a Places photo resource name to a CDN URL (soft fail)."""
        name = normalize_places_photo_name(photo_name)
        if not name or not self._api_key:
            return None
        height = max(100, min(int(max_height_px), 1600))
        encoded = urllib.parse.quote(name, safe="/")
        qs = urllib.parse.urlencode(
            {
                "maxHeightPx": str(height),
                "skipHttpRedirect": "true",
                "key": self._api_key,
            }
        )
        url = f"https://places.googleapis.com/v1/{encoded}/media?{qs}"
        req = urllib.request.Request(
            url,
            method="GET",
            headers={"X-Goog-Api-Key": self._api_key},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_sec) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:  # noqa: BLE001
                body = ""
            logger.warning(
                "places photo media HTTP %s: %s",
                exc.code,
                body or exc.reason,
            )
            return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning("places photo media failed: %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("places photo media unexpected error: %s", exc)
            return None
        if not isinstance(payload, dict):
            return None
        uri = str(payload.get("photoUri") or "").strip()
        return uri or None

    def fetch_photo_bytes(
        self, photo_name: str, *, max_height_px: int = 640
    ) -> tuple[bytes, str, str] | None:
        """Download photo bytes via Places media → CDN (server-side, no browser Referer).

        Returns ``(bytes, content_type, photo_uri)`` or ``None``.
        """
        uri = self.photo_media_uri(photo_name, max_height_px=max_height_px)
        if not uri:
            return None
        req = urllib.request.Request(
            uri,
            method="GET",
            headers={"User-Agent": "vacation-planner/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_sec) as resp:
                data = resp.read()
                if not data:
                    return None
                content_type = (
                    str(resp.headers.get("Content-Type") or "").split(";")[0].strip()
                    or "image/jpeg"
                )
                if not content_type.startswith("image/"):
                    content_type = "image/jpeg"
                return data, content_type, uri
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning("places CDN fetch failed: %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("places CDN fetch unexpected error: %s", exc)
            return None

    def first_photo_name_for_place_id(self, place_id: str) -> str | None:
        """Load place details (New) and return the first photo resource name."""
        pid = normalize_place_id(place_id)
        if not pid or not self._api_key:
            return None
        url = f"https://places.googleapis.com/v1/places/{urllib.parse.quote(pid, safe='')}"
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "X-Goog-Api-Key": self._api_key,
                "X-Goog-FieldMask": PLACE_DETAILS_FIELD_MASK,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_sec) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:  # noqa: BLE001
                body = ""
            logger.warning(
                "places get details HTTP %s for %s: %s",
                exc.code,
                pid[:24],
                body or exc.reason,
            )
            return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning("places get details failed for %s: %s", pid[:24], exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "places get details unexpected error for %s: %s", pid[:24], exc
            )
            return None
        if not isinstance(payload, dict):
            return None
        name = _first_photo_name(payload)
        if not name:
            photos = payload.get("photos")
            count = len(photos) if isinstance(photos, list) else 0
            logger.info(
                "places details has no usable photos for %s (photos=%s)",
                pid[:24],
                count,
            )
        return name

    def fetch_legacy_photo_bytes(
        self, place_id: str, *, max_width_px: int = 640
    ) -> tuple[bytes, str, str] | None:
        """Fallback: Places API (legacy) details photo_reference → photo bytes.

        Some keys return place IDs via Places API (New) Text Search but empty
        ``photos`` on Place Details (New). Legacy Place Photo still works for
        many of those keys and returns image bytes directly.
        """
        pid = normalize_place_id(place_id)
        if not pid or not self._api_key:
            return None
        width = max(100, min(int(max_width_px), 1600))
        details_qs = urllib.parse.urlencode(
            {
                "place_id": pid,
                "fields": "photos",
                "key": self._api_key,
            }
        )
        details_req = urllib.request.Request(
            f"{LEGACY_DETAILS_URL}?{details_qs}",
            method="GET",
        )
        try:
            with urllib.request.urlopen(details_req, timeout=self._timeout_sec) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning("legacy place details failed for %s: %s", pid[:24], exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "legacy place details unexpected error for %s: %s", pid[:24], exc
            )
            return None

        if not isinstance(payload, dict) or payload.get("status") not in {
            "OK",
            "ZERO_RESULTS",
        }:
            logger.info(
                "legacy place details status=%s for %s",
                (payload or {}).get("status") if isinstance(payload, dict) else None,
                pid[:24],
            )
            return None
        result = payload.get("result") if isinstance(payload, dict) else None
        photos = result.get("photos") if isinstance(result, dict) else None
        if not isinstance(photos, list) or not photos:
            logger.info("legacy place details has no photos for %s", pid[:24])
            return None
        first = photos[0] if isinstance(photos[0], dict) else None
        ref = str((first or {}).get("photo_reference") or "").strip()
        if not ref:
            return None

        photo_qs = urllib.parse.urlencode(
            {
                "maxwidth": str(width),
                "photo_reference": ref,
                "key": self._api_key,
            }
        )
        photo_req = urllib.request.Request(
            f"{LEGACY_PHOTO_URL}?{photo_qs}",
            method="GET",
            headers={"User-Agent": "vacation-planner/1.0"},
        )
        try:
            with urllib.request.urlopen(photo_req, timeout=self._timeout_sec) as resp:
                data = resp.read()
                if not data:
                    return None
                content_type = (
                    str(resp.headers.get("Content-Type") or "").split(";")[0].strip()
                    or "image/jpeg"
                )
                if not content_type.startswith("image/"):
                    content_type = "image/jpeg"
                final_url = str(resp.geturl() or "")
                return data, content_type, final_url
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning("legacy place photo failed for %s: %s", pid[:24], exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "legacy place photo unexpected error for %s: %s", pid[:24], exc
            )
            return None


def normalize_places_photo_name(photo_name: str | None) -> str | None:
    raw = str(photo_name or "").strip().lstrip("/")
    if not raw:
        return None
    # Media responses sometimes append /media to the photo resource name.
    if raw.endswith("/media"):
        raw = raw[: -len("/media")]
    if ".." in raw or not _PHOTO_NAME_RE.match(raw):
        return None
    return raw


def normalize_place_id(place_id: str | None) -> str | None:
    raw = str(place_id or "").strip()
    if raw.startswith("places/"):
        raw = raw.removeprefix("places/")
    if not raw or not _PLACE_ID_RE.match(raw):
        return None
    return raw


def is_usable_google_place_id(
    place_id: str | None, *, place_key: str | None = None
) -> bool:
    """True when ``place_id`` looks like a real Google Places ID.

    Crews often invent slug ids (``teamlab-borderless``, ``asakusa_senso_ji``)
    or numeric placeholders (``1``) that pass the charset regex but are useless
    for Photos / Details.
    """
    pid = normalize_place_id(place_id)
    if not pid:
        return False
    key = str(place_key or "").strip()
    if key and pid == key:
        return False
    if pid.isdigit():
        return False
    # Slug-style ids: lowercase with separators, not classic ChIJ… tokens.
    if pid == pid.lower() and not pid.startswith("ChIJ"):
        if "-" in pid or "_" in pid:
            return False
    return True


def resolve_place_photo_uri(
    *,
    photo_name: str | None = None,
    place_id: str | None = None,
    client: GooglePlacesClient | None = None,
    max_height_px: int = 640,
) -> tuple[str | None, str | None]:
    """Return (photo_uri, places_photo_name). Soft-fails to (None, None)."""
    active = client
    if active is None:
        key = places_api_key_from_env()
        if not key:
            return None, None
        active = GooglePlacesClient(key)

    name = normalize_places_photo_name(photo_name)
    if not name and place_id:
        name = active.first_photo_name_for_place_id(place_id)
    if not name:
        return None, None
    uri = active.photo_media_uri(name, max_height_px=max_height_px)
    if not uri:
        return None, name
    return uri, name


def resolve_place_photo_payload(
    *,
    photo_name: str | None = None,
    place_id: str | None = None,
    client: GooglePlacesClient | None = None,
    max_height_px: int = 640,
    include_bytes: bool = True,
) -> dict[str, str | None]:
    """Resolve photo URI and optionally embed image bytes as a data URL.

    Browser ``<img>`` tags often get 403 from googleusercontent when a Referer
    is sent; a data URL from server-fetched bytes avoids that entirely.

    Order: Places API (New) photo media → legacy Place Photo by ``place_id``.
    """
    empty = {
        "photo_url": None,
        "places_photo_name": None,
        "photo_data_url": None,
    }
    cache_key = "|".join(
        [
            normalize_places_photo_name(photo_name) or "",
            normalize_place_id(place_id) or "",
            str(max_height_px),
            "1" if include_bytes else "0",
        ]
    )
    if client is None and cache_key.strip("|"):
        cached = _PHOTO_PAYLOAD_CACHE.get(cache_key)
        if cached is not None:
            ts, payload = cached
            if time.monotonic() - ts <= _PHOTO_CACHE_TTL_SEC:
                return dict(payload)

    active = client
    if active is None:
        key = places_api_key_from_env()
        if not key:
            return empty
        active = GooglePlacesClient(key)

    name = normalize_places_photo_name(photo_name)
    if not name and place_id:
        name = active.first_photo_name_for_place_id(place_id)
        if name:
            name = normalize_places_photo_name(name)

    result = dict(empty)
    if name:
        if include_bytes:
            fetched = active.fetch_photo_bytes(name, max_height_px=max_height_px)
            if fetched is not None:
                data, content_type, uri = fetched
                photo_data_url: str | None = None
                if len(data) <= 220_000:
                    b64 = base64.b64encode(data).decode("ascii")
                    photo_data_url = f"data:{content_type};base64,{b64}"
                result = {
                    "photo_url": uri,
                    "places_photo_name": name,
                    "photo_data_url": photo_data_url,
                }
        if not result.get("photo_data_url") and not result.get("photo_url"):
            uri = active.photo_media_uri(name, max_height_px=max_height_px)
            result = {
                "photo_url": uri,
                "places_photo_name": name,
                "photo_data_url": None,
            }

    # Legacy Place Photo when New API has no photo resource / media fails.
    if (
        include_bytes
        and place_id
        and not result.get("photo_data_url")
        and not result.get("photo_url")
        and hasattr(active, "fetch_legacy_photo_bytes")
    ):
        legacy = active.fetch_legacy_photo_bytes(  # type: ignore[attr-defined]
            place_id, max_width_px=max_height_px
        )
        if legacy is not None:
            data, content_type, uri = legacy
            photo_data_url = None
            if len(data) <= 220_000:
                b64 = base64.b64encode(data).decode("ascii")
                photo_data_url = f"data:{content_type};base64,{b64}"
            result = {
                "photo_url": uri or None,
                "places_photo_name": name,
                "photo_data_url": photo_data_url,
            }

    if (
        client is None
        and cache_key.strip("|")
        and (result.get("photo_data_url") or result.get("photo_url"))
    ):
        _PHOTO_PAYLOAD_CACHE[cache_key] = (time.monotonic(), dict(result))
    return result


def places_api_key_from_env() -> str:
    from services.secrets import resolve_secret

    return resolve_secret(
        plain_env="GOOGLE_PLACES_API_KEY",
        arn_env="GOOGLE_PLACES_SECRET_ARN",
    )


def get_places_client() -> GooglePlacesClient | None:
    key = places_api_key_from_env()
    if not key:
        return None
    return GooglePlacesClient(key)


def places_enrich_enabled() -> bool:
    """Kill switch: PLACES_ENRICH=off disables enrichment even when a key is set."""
    flag = os.getenv("PLACES_ENRICH", "on").strip().lower()
    return flag not in {"off", "0", "false", "no"}
