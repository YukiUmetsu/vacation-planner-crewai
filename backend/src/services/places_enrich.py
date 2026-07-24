"""Enrich crew places with Google Places open-status / weekday hours (soft)."""

from __future__ import annotations

import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from db.place_keys import normalize_place_text
from services.places_client import (
    GooglePlacesClient,
    PlacesClient,
    PlacesLookupResult,
    format_places_cost,
    is_usable_google_place_id,
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
            # Newlines parse cleanly in the place-detail UI.
            return "\n".join(lines)
    return None


_NAME_STOPWORDS = frozenset(
    {
        "and",
        "or",
        "the",
        "a",
        "an",
        "of",
        "at",
        "in",
        "on",
        "to",
        "for",
        "with",
        "near",
    }
)
# Treat these as interchangeable venue-type words (Meiji Shrine ≈ Meiji Jingu).
_TYPE_SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"shrine", "jingu", "jinja", "temple", "ji", "dera", "san"}),
    frozenset({"park", "garden", "gardens"}),
    frozenset({"museum", "gallery"}),
    frozenset({"market", "bazaar"}),
    frozenset({"station", "terminal"}),
    frozenset({"crossing", "scramble", "intersection"}),
)
_VAGUE_ADDRESS_MARKERS = (
    "various",
    "along the",
    "multiple",
    "several",
    "see website",
    "tbd",
    "n/a",
    "na",
    "unknown",
)
# JP postal ``123-4567`` / compact ``1234567``; also US ZIP and generic digit runs.
_POSTAL_RE = re.compile(r"\b(\d{3}-?\d{4}|\d{5}(?:-\d{4})?)\b")
# Coarse area words we keep from crew addresses (wards / neighborhoods), not street numbers.
_AREA_STOPWORDS = frozenset(
    {
        "city",
        "ward",
        "ku",
        "cho",
        "chome",
        "pref",
        "prefecture",
        "japan",
        "ken",
        "street",
        "st",
        "ave",
        "road",
        "rd",
        "building",
        "bldg",
        "floor",
        "fl",
    }
)


def _name_tokens(value: str | None) -> set[str]:
    """Normalize a venue name into comparable tokens (drop stopwords / hyphens)."""
    folded = unicodedata.normalize("NFKD", value or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    text = normalize_place_text(folded).replace("-", " ").replace("_", " ")
    return {
        tok
        for tok in text.split()
        if tok and tok not in _NAME_STOPWORDS and len(tok) >= 2
    }


def _type_tokens(tokens: set[str]) -> set[str]:
    out: set[str] = set()
    for tok in tokens:
        for group in _TYPE_SYNONYM_GROUPS:
            if tok in group:
                out.add(tok)
                break
    return out


def _core_tokens(tokens: set[str]) -> set[str]:
    return tokens - _type_tokens(tokens)


def names_match(crew_name: str, display_name: str | None) -> bool:
    """Require a plausible Text Search hit before overwriting crew fields."""
    a = _name_tokens(crew_name)
    b = _name_tokens(display_name)
    if not a or not b:
        return False
    if a == b:
        return True
    if a <= b or b <= a:
        return True
    overlap = a & b
    if len(overlap) >= 2:
        return True
    if len(overlap) == 1 and len(next(iter(overlap))) >= 5:
        return True
    core_a, core_b = _core_tokens(a), _core_tokens(b)
    core_overlap = core_a & core_b
    if core_overlap and (
        not _type_tokens(a)
        or not _type_tokens(b)
        or any(
            _type_tokens(a) & group and _type_tokens(b) & group
            for group in _TYPE_SYNONYM_GROUPS
        )
    ):
        if any(len(tok) >= 4 for tok in core_overlap):
            return True
    return False


def name_overlap_score(crew_name: str, display_name: str | None) -> int:
    """Higher = closer name match; used to pick among several Text hits."""
    a = _name_tokens(crew_name)
    b = _name_tokens(display_name)
    if not a or not b:
        return 0
    overlap = a & b
    score = len(overlap) * 10
    if a == b:
        score += 50
    elif a <= b or b <= a:
        score += 25
    core_overlap = _core_tokens(a) & _core_tokens(b)
    score += len(core_overlap) * 5
    score -= max(0, len(b - a) - 2)
    return score


def _postal_codes(text: str | None) -> set[str]:
    """Normalized postal / ZIP codes found in an address string."""
    raw = str(text or "")
    out: set[str] = set()
    for match in _POSTAL_RE.finditer(raw):
        digits = re.sub(r"\D", "", match.group(1))
        if digits:
            out.add(digits)
    return out


def _area_tokens(address: str | None) -> set[str]:
    """Ward / neighborhood tokens from an address (ignore street numbers & house codes)."""
    text = normalize_place_text(address).replace("-", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    tokens: set[str] = set()
    for tok in text.split():
        if not tok or tok in _AREA_STOPWORDS or tok in _NAME_STOPWORDS:
            continue
        if tok.isdigit() or re.fullmatch(r"\d+[a-z]?", tok):
            continue
        if len(tok) < 3:
            continue
        tokens.add(tok)
    return tokens


def _address_is_vague(address: str) -> bool:
    raw = normalize_place_text(address)
    if not raw:
        return True
    if any(marker in raw for marker in _VAGUE_ADDRESS_MARKERS):
        return True
    return not _postal_codes(address) and not _area_tokens(address)


def location_compatible(
    *,
    crew_address: str,
    overnight_city: str,
    formatted_address: str | None,
) -> bool:
    """Coarse location check: postal code, overnight city, or ward/area overlap.

    Intentionally ignores detailed street / chome matching — those strings rarely
    agree across crew output and Google ``formattedAddress``.
    """
    city = normalize_place_text(overnight_city)
    fmt = normalize_place_text(formatted_address)
    # Text Search occasionally omits formattedAddress; if we scoped the query with
    # an overnight city, treat a missing address as city-compatible.
    if not fmt:
        return bool(city)

    city_ok = bool(city) and city in fmt

    crew_postals = _postal_codes(crew_address)
    hit_postals = _postal_codes(formatted_address)
    if crew_postals and hit_postals and crew_postals & hit_postals:
        return True

    if crew_address and not _address_is_vague(crew_address):
        areas = _area_tokens(crew_address)
        if areas and any(tok in fmt for tok in areas):
            return True

    if city_ok:
        return True

    return False


def pick_matching_lookup(
    crew_name: str,
    candidates: list[PlacesLookupResult],
    *,
    crew_address: str = "",
    overnight_city: str = "",
    loose: bool = False,
) -> PlacesLookupResult | None:
    """Pick the best Text Search hit by name + location.

    Falls back to a sole city-compatible hit when the display name is localized
    (``明治神宮``) or uses an alternate English form.

    When ``loose=True`` (photo resolve), also accept the best city-compatible hit
    even with weak name overlap — photos are soft UX, not quality gates.
    """
    best: PlacesLookupResult | None = None
    best_score = -1
    location_hits: list[PlacesLookupResult] = []
    for candidate in candidates:
        if location_compatible(
            crew_address=crew_address,
            overnight_city=overnight_city,
            formatted_address=candidate.formatted_address,
        ):
            location_hits.append(candidate)
        if not names_match(crew_name, candidate.display_name):
            continue
        if candidate not in location_hits:
            continue
        score = name_overlap_score(crew_name, candidate.display_name)
        if score > best_score:
            best = candidate
            best_score = score
    if best is not None:
        return best

    if not location_hits:
        # Last resort for photo: sole Text hit when city was in the query.
        if loose and len(candidates) == 1 and overnight_city.strip():
            return candidates[0]
        return None

    # Soft: best location-compatible hit with any positive name overlap.
    soft: list[tuple[int, PlacesLookupResult]] = []
    for candidate in location_hits:
        score = name_overlap_score(crew_name, candidate.display_name)
        if score > 0:
            soft.append((score, candidate))
    if soft:
        soft.sort(key=lambda item: item[0], reverse=True)
        return soft[0][1]

    # Sole in-city hit: allow localized display names (no Latin script) or when a
    # crew core token appears in the formatted address (e.g. Asakusa in address).
    if len(location_hits) == 1:
        only = location_hits[0]
        display = str(only.display_name or "")
        if display and not re.search(r"[A-Za-z]{3,}", display):
            return only
        fmt = normalize_place_text(only.formatted_address)
        cores = _core_tokens(_name_tokens(crew_name))
        if fmt and any(len(tok) >= 4 and tok in fmt for tok in cores):
            return only
        if loose:
            return only

    if loose and location_hits:
        # Prefer the hit whose display name shares the most tokens; else first.
        ranked = sorted(
            location_hits,
            key=lambda c: name_overlap_score(crew_name, c.display_name),
            reverse=True,
        )
        return ranked[0]
    return None


def apply_lookup_to_place(
    place: dict[str, Any],
    lookup: PlacesLookupResult,
    *,
    photo_uri: str | None = None,
) -> dict[str, Any]:
    """Merge Places lookup into a place dict (does not mutate input)."""
    out = {**place}
    status = map_business_status(lookup.business_status)
    out["operational_status"] = status

    if lookup.place_id:
        existing = str(out.get("place_id") or "").strip()
        if not is_usable_google_place_id(
            existing, place_key=str(out.get("place_key") or "") or None
        ):
            out["place_id"] = lookup.place_id

    if lookup.formatted_address and not str(out.get("address") or "").strip():
        out["address"] = lookup.formatted_address

    closed = closed_weekdays_from_hours(lookup.regular_opening_hours)
    if closed is not None:
        out["closed_weekdays"] = closed

    hours_text = open_hours_text(lookup.regular_opening_hours)
    if hours_text:
        out["open_hours"] = hours_text

    cost = format_places_cost(lookup.price_level, lookup.price_range)
    if cost and not str(out.get("cost") or "").strip():
        out["cost"] = cost

    if lookup.photo_name:
        out["places_photo_name"] = lookup.photo_name

    # Always refresh when we resolved a URI — stored CDN links expire.
    if photo_uri:
        out["photo_url"] = photo_uri

    return out


def _build_query(place: dict[str, Any], overnight_city: str) -> str:
    """Prefer name + city — long crew street addresses confuse Text Search."""
    name = str(place.get("name") or "").strip()
    city = overnight_city.strip()
    if name and city:
        return f"{name}, {city}"
    address = str(place.get("address") or "").strip()
    if name and address:
        return f"{name}, {address}"
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
    loose_match: bool = False,
) -> dict[str, Any]:
    """Enrich one place via Places Text Search. Soft no-op when disabled / no match.

    ``loose_match=True`` relaxes hit picking for on-demand photo resolve.
    """
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
        loose=loose_match,
    )
    if lookup is None:
        if candidates:
            sample = ", ".join(
                repr(c.display_name) for c in candidates[:3] if c.display_name
            )
            logger.info(
                "places enrich skipped: no confident match for %r among %d hits"
                " (top: %s)",
                name,
                len(candidates),
                sample or "—",
            )
        else:
            logger.info("places enrich skipped: no Text Search hits for %r", query[:80])
        return place

    photo_uri: str | None = None
    photo_name = lookup.photo_name
    if not photo_name and lookup.place_id and hasattr(
        active_client, "first_photo_name_for_place_id"
    ):
        try:
            photo_name = active_client.first_photo_name_for_place_id(  # type: ignore[attr-defined]
                lookup.place_id
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("places photo name lookup failed for %r: %s", name, exc)
            photo_name = None
    if photo_name and hasattr(active_client, "photo_media_uri"):
        try:
            photo_uri = active_client.photo_media_uri(photo_name)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            logger.warning("places photo resolve failed for %r: %s", name, exc)
            photo_uri = None

    # Ensure apply_lookup persists the photo resource name even if CDN resolve failed.
    if photo_name and not lookup.photo_name:
        lookup = PlacesLookupResult(
            place_id=lookup.place_id,
            business_status=lookup.business_status,
            formatted_address=lookup.formatted_address,
            display_name=lookup.display_name,
            regular_opening_hours=lookup.regular_opening_hours,
            price_level=lookup.price_level,
            price_range=lookup.price_range,
            photo_name=photo_name,
        )

    return apply_lookup_to_place(place, lookup, photo_uri=photo_uri)


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
