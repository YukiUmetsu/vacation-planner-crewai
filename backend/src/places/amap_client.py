"""Amap (高德) Place Text Search client for mainland China enrichment."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from places.client import (
    DEFAULT_MAX_RESULTS,
    DEFAULT_TIMEOUT_SEC,
    PlacesLookupResult,
    PlacesTransientError,
    is_http_transient,
    raise_if_http_transient,
)

logger = logging.getLogger(__name__)

AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text"
AMAP_ID_PREFIX = "amap:"


def amap_api_key_from_env() -> str:
    from ops.secrets import resolve_secret

    return resolve_secret(
        plain_env="AMAP_WEB_KEY",
        arn_env="AMAP_WEB_SECRET_ARN",
    )


def is_amap_place_id(place_id: str | None) -> bool:
    raw = str(place_id or "").strip()
    return raw.startswith(AMAP_ID_PREFIX) and len(raw) > len(AMAP_ID_PREFIX)


def amap_maps_url(*, name: str, lng: float | None, lat: float | None) -> str | None:
    """Web URI suitable for link + simple embed query."""
    label = urllib.parse.quote(name.strip() or "place")
    if lng is not None and lat is not None:
        return (
            f"https://uri.amap.com/marker?position={lng},{lat}"
            f"&name={label}&coordinate=gaode&callnative=0"
        )
    if name.strip():
        return f"https://uri.amap.com/search?keyword={label}&callnative=0"
    return None


def _parse_location(raw: Any) -> tuple[float | None, float | None]:
    text = str(raw or "").strip()
    if not text or "," not in text:
        return None, None
    lng_s, lat_s = text.split(",", 1)
    try:
        return float(lng_s.strip()), float(lat_s.strip())
    except ValueError:
        return None, None


def _amap_open_time_text(raw: dict[str, Any]) -> str | None:
    """Pull human hours from common Amap Place Text fields."""
    candidates: list[Any] = [
        raw.get("business_hours"),
        raw.get("opentime"),
        raw.get("opentime2"),
        raw.get("opentime_week"),
        raw.get("opentime_today"),
    ]
    biz_ext = raw.get("biz_ext")
    if isinstance(biz_ext, dict):
        candidates.extend(
            [
                biz_ext.get("open_time"),
                biz_ext.get("opentime"),
                biz_ext.get("time"),
            ]
        )
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value:
            joined = "; ".join(str(x).strip() for x in value if str(x).strip())
            if joined:
                return joined
    return None


def _parse_poi(raw: dict[str, Any]) -> PlacesLookupResult | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip() or None
    address = str(raw.get("address") or "").strip() or None
    city = str(raw.get("cityname") or "").strip()
    if address and city and city not in address:
        address = f"{address}, {city}"
    elif not address and city:
        address = city
    poi_id = str(raw.get("id") or "").strip()
    place_id = f"{AMAP_ID_PREFIX}{poi_id}" if poi_id else None
    lng, lat = _parse_location(raw.get("location"))
    # Do not invent OPERATIONAL — Amap rarely reports status; keep unknown.
    business_status = None
    hours_text = _amap_open_time_text(raw)
    open_hours = {"amap_text": hours_text} if hours_text else None

    return PlacesLookupResult(
        place_id=place_id,
        business_status=business_status,
        formatted_address=address,
        display_name=name,
        regular_opening_hours=open_hours,
        price_level=None,
        price_range=None,
        photo_name=None,
        lat=lat,
        lng=lng,
        provider="amap",
        maps_url=amap_maps_url(name=name or "", lng=lng, lat=lat),
        open_hours_text=hours_text,
        raw_extra=None,
    )


class AmapPlacesClient:
    """Text search against Amap Web Service Place API."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        city: str = "",
    ) -> None:
        self._api_key = api_key.strip()
        self._timeout = timeout_sec
        self._city = city.strip()

    def search_text(
        self, text_query: str, *, max_results: int = DEFAULT_MAX_RESULTS
    ) -> list[PlacesLookupResult]:
        query = text_query.strip()
        if not query or not self._api_key:
            return []
        params: dict[str, str] = {
            "key": self._api_key,
            "keywords": query,
            "offset": str(max(1, min(25, max_results))),
            "page": "1",
            "extensions": "all",
        }
        if self._city:
            params["city"] = self._city
            params["citylimit"] = "true"
        url = f"{AMAP_PLACE_TEXT_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise_if_http_transient(exc, what="Amap Place Text")
            logger.warning("Amap search HTTP %s for %r", exc.code, query[:80])
            return []
        except Exception as exc:  # noqa: BLE001
            if is_http_transient(getattr(exc, "code", None)):
                raise PlacesTransientError(str(exc)) from exc
            logger.warning("Amap search failed for %r: %s", query[:80], exc)
            return []

        if not isinstance(body, dict) or str(body.get("status")) != "1":
            info = body.get("info") if isinstance(body, dict) else None
            logger.info("Amap search empty/error for %r: %s", query[:80], info)
            return []

        pois = body.get("pois")
        if not isinstance(pois, list):
            return []
        out: list[PlacesLookupResult] = []
        for raw in pois[: max(1, max_results)]:
            if not isinstance(raw, dict):
                continue
            parsed = _parse_poi(raw)
            if parsed is not None:
                out.append(parsed)
        return out
