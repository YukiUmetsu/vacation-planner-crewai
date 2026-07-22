"""Google Places API (New) Text Search client for venue open-status."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

SEARCH_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.businessStatus,places.regularOpeningHours"
)
DEFAULT_TIMEOUT_SEC = 4.0
DEFAULT_MAX_RESULTS = 5


@dataclass(frozen=True)
class PlacesLookupResult:
    place_id: str | None
    business_status: str | None
    formatted_address: str | None
    display_name: str | None
    regular_opening_hours: dict[str, Any] | None


class PlacesClient(Protocol):
    def search_text(
        self, text_query: str, *, max_results: int = DEFAULT_MAX_RESULTS
    ) -> list[PlacesLookupResult]: ...


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

        places = payload.get("places") if isinstance(payload, dict) else None
        if not isinstance(places, list) or not places:
            return []

        out: list[PlacesLookupResult] = []
        for item in places:
            parsed = _parse_place(item) if isinstance(item, dict) else None
            if parsed is not None:
                out.append(parsed)
        return out


def places_api_key_from_env() -> str:
    return os.getenv("GOOGLE_PLACES_API_KEY", "").strip()


def places_enrich_enabled() -> bool:
    """Kill switch: PLACES_ENRICH=off disables enrichment even when a key is set."""
    flag = os.getenv("PLACES_ENRICH", "on").strip().lower()
    return flag not in {"off", "0", "false", "no"}
