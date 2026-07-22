"""Enrich crew places with Google Places open-status / weekday hours (soft)."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from db.place_keys import normalize_place_text
from services.places_client import (
    GooglePlacesClient,
    PlacesClient,
    PlacesLookupResult,
    places_api_key_from_env,
    places_enrich_enabled,
)

logger = logging.getLogger(__name__)

# Google Places OpeningHours day: Sunday=0 … Saturday=6
# Our closed_weekdays: Monday=0 … Sunday=6 (datetime.date.weekday())
_ALL_PYTHON_WEEKDAYS = frozenset(range(7))
_MAX_PARALLEL = 4


def google_day_to_python_weekday(google_day: int) -> int:
    return (int(google_day) + 6) % 7


def map_business_status(status: str | None) -> str:
    """Map Google businessStatus → operational_status."""
    raw = (status or "").strip().upper()
    if raw in {"CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY", "FUTURE_OPENING"}:
        return "closed"
    if raw == "OPERATIONAL":
        return "open"
    return "unknown"


def is_always_open_hours(hours: dict[str, Any] | None) -> bool:
    """Google 24/7: one period open day=0 hour=0 minute=0 with no close."""
    if not hours or not isinstance(hours, dict):
        return False
    periods = hours.get("periods")
    if not isinstance(periods, list) or len(periods) != 1:
        return False
    period = periods[0]
    if not isinstance(period, dict):
        return False
    # Always-open has no close object (key absent or null).
    if period.get("close") is not None:
        return False
    open_info = period.get("open")
    if not isinstance(open_info, dict):
        return False
    try:
        day = int(open_info.get("day"))
        hour = int(open_info.get("hour", -1))
        minute = int(open_info.get("minute", -1))
    except (TypeError, ValueError):
        return False
    return day == 0 and hour == 0 and minute == 0


def closed_weekdays_from_hours(hours: dict[str, Any] | None) -> list[int] | None:
    """Return Mon=0..Sun=6 closed days from regularOpeningHours, or None if unknown."""
    if not hours or not isinstance(hours, dict):
        return None
    if is_always_open_hours(hours):
        return []

    periods = hours.get("periods")
    if not isinstance(periods, list) or not periods:
        return None

    open_python: set[int] = set()
    for period in periods:
        if not isinstance(period, dict):
            continue
        open_info = period.get("open")
        if not isinstance(open_info, dict):
            continue
        day = open_info.get("day")
        try:
            gday = int(day)
        except (TypeError, ValueError):
            continue
        if 0 <= gday <= 6:
            open_python.add(google_day_to_python_weekday(gday))

    if not open_python:
        return None
    return sorted(_ALL_PYTHON_WEEKDAYS - open_python)


def open_hours_text(hours: dict[str, Any] | None) -> str | None:
    if not hours or not isinstance(hours, dict):
        return None
    if is_always_open_hours(hours):
        return "Open 24 hours"
    descriptions = hours.get("weekdayDescriptions")
    if isinstance(descriptions, list) and descriptions:
        lines = [str(line).strip() for line in descriptions if str(line).strip()]
        if lines:
            return "; ".join(lines)
    return None


def names_match(crew_name: str, display_name: str | None) -> bool:
    """Require a plausible Text Search hit before overwriting crew fields."""
    a = normalize_place_text(crew_name)
    b = normalize_place_text(display_name)
    if not a or not b:
        return False
    if a == b:
        return True
    # Token containment (avoids "park" matching "parking").
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return False
    shorter, longer = (
        (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)
    )
    return shorter <= longer


def _significant_tokens(text: str) -> list[str]:
    return [tok for tok in text.split() if len(tok) >= 2]


def location_compatible(
    *,
    crew_address: str,
    overnight_city: str,
    formatted_address: str | None,
) -> bool:
    """
    Require city/address evidence before trusting a Text Search hit.

    Common names (Starbucks, Museum) often return the wrong branch; without a
    formattedAddress that overlaps overnight_city or crew address, refuse.
    """
    fmt = normalize_place_text(formatted_address)
    if not fmt:
        return False

    city = normalize_place_text(overnight_city)
    addr = normalize_place_text(crew_address)
    city_ok = bool(city) and city in fmt

    if addr:
        tokens = _significant_tokens(addr)
        if not tokens:
            return city_ok
        overlap = sum(1 for tok in tokens if tok in fmt)
        # Need real address overlap; city alone is not enough when crew gave an address
        # (avoids closed Osaka Starbucks matching a Tokyo address that also says "Japan").
        need = 1 if len(tokens) == 1 else min(2, len(tokens))
        if overlap >= need:
            return True
        return False

    if city:
        return city_ok

    # No location anchors from the crew → too ambiguous for status overwrite.
    return False


def pick_matching_lookup(
    crew_name: str,
    candidates: list[PlacesLookupResult],
    *,
    crew_address: str = "",
    overnight_city: str = "",
) -> PlacesLookupResult | None:
    for candidate in candidates:
        if not names_match(crew_name, candidate.display_name):
            continue
        if location_compatible(
            crew_address=crew_address,
            overnight_city=overnight_city,
            formatted_address=candidate.formatted_address,
        ):
            return candidate
    return None


def apply_lookup_to_place(
    place: dict[str, Any],
    lookup: PlacesLookupResult,
) -> dict[str, Any]:
    """Merge Places lookup into a place dict (does not mutate input)."""
    out = {**place}
    status = map_business_status(lookup.business_status)
    out["operational_status"] = status

    if lookup.place_id and not str(out.get("place_id") or "").strip():
        out["place_id"] = lookup.place_id

    if lookup.formatted_address and not str(out.get("address") or "").strip():
        out["address"] = lookup.formatted_address

    closed = closed_weekdays_from_hours(lookup.regular_opening_hours)
    if closed is not None:
        out["closed_weekdays"] = closed

    hours_text = open_hours_text(lookup.regular_opening_hours)
    if hours_text:
        out["open_hours"] = hours_text

    return out


def _build_query(place: dict[str, Any], overnight_city: str) -> str:
    name = str(place.get("name") or "").strip()
    address = str(place.get("address") or "").strip()
    city = overnight_city.strip()
    if name and address:
        return f"{name}, {address}"
    if name and city:
        return f"{name}, {city}"
    return name or address or city


def _needs_places_lookup(place: dict[str, Any]) -> bool:
    """Skip HTTP when crew already marked permanently closed (quality will drop it)."""
    status = str(place.get("operational_status") or "unknown").strip().lower()
    return status != "closed"


def enrich_place(
    place: dict[str, Any],
    *,
    overnight_city: str = "",
    client: PlacesClient | None = None,
) -> dict[str, Any]:
    """Enrich one place via Places Text Search. Soft no-op when disabled / no match."""
    if not places_enrich_enabled():
        return place
    if not _needs_places_lookup(place):
        return place

    active_client = client
    if active_client is None:
        key = places_api_key_from_env()
        if not key:
            return place
        active_client = GooglePlacesClient(key)

    name = str(place.get("name") or "").strip()
    query = _build_query(place, overnight_city)
    if not query or not name:
        return place

    try:
        candidates = active_client.search_text(query)
    except Exception as exc:  # noqa: BLE001 — soft enrich boundary
        logger.warning("places enrich failed for %r: %s", query, exc)
        return place

    lookup = pick_matching_lookup(
        name,
        candidates,
        crew_address=str(place.get("address") or ""),
        overnight_city=overnight_city,
    )
    if lookup is None:
        if candidates:
            logger.info(
                "places enrich skipped: no confident match for %r among %d hits",
                name,
                len(candidates),
            )
        return place
    return apply_lookup_to_place(place, lookup)


def enrich_places(
    places: list[dict[str, Any]],
    *,
    overnight_city: str = "",
    client: PlacesClient | None = None,
) -> list[dict[str, Any]]:
    """Enrich places in parallel (bounded). Soft no-op when Places is off or key missing."""
    if not places:
        return places
    if not places_enrich_enabled():
        return places

    active_client = client
    if active_client is None:
        key = places_api_key_from_env()
        if not key:
            return places
        active_client = GooglePlacesClient(key)

    # Preserve order; parallelize only places that need a lookup.
    results: list[dict[str, Any] | None] = [None] * len(places)
    work: list[tuple[int, dict[str, Any]]] = []
    for idx, place in enumerate(places):
        if _needs_places_lookup(place):
            work.append((idx, place))
        else:
            results[idx] = place

    if not work:
        return places

    def _run(item: tuple[int, dict[str, Any]]) -> tuple[int, dict[str, Any]]:
        i, p = item
        return i, enrich_place(p, overnight_city=overnight_city, client=active_client)

    workers = min(_MAX_PARALLEL, len(work))
    if workers == 1:
        for item in work:
            i, enriched = _run(item)
            results[i] = enriched
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_run, item) for item in work]
            for fut in as_completed(futures):
                i, enriched = fut.result()
                results[i] = enriched

    return [r if r is not None else places[i] for i, r in enumerate(results)]
