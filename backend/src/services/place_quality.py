"""Post-crew place quality gates (closed venues, weekday hours, energy load)."""

from __future__ import annotations

from datetime import date
from typing import Any

from db.place_keys import normalize_place_text
from http_utils import ApiError
from services.dedupe import ensure_place_key


def _parse_nonneg_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _closed_weekdays(place: dict[str, Any]) -> set[int]:
    raw = place.get("closed_weekdays") or []
    if not isinstance(raw, list):
        return set()
    out: set[int] = set()
    for item in raw:
        try:
            day = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= day <= 6:
            out.add(day)
    return out


def place_total_minutes(place: dict[str, Any]) -> int:
    return _parse_nonneg_int(place.get("estimated_minutes")) + _parse_nonneg_int(
        place.get("travel_minutes_from_previous")
    )


def day_total_minutes(places: list[dict[str, Any]]) -> int:
    return sum(place_total_minutes(p) for p in places)


def is_permanently_closed(place: dict[str, Any]) -> bool:
    status = str(place.get("operational_status") or "unknown").strip().lower()
    return status == "closed"


def is_closed_on_date(place: dict[str, Any], day: date) -> bool:
    return day.weekday() in _closed_weekdays(place)


def profile_visited_name_keys(visited_places: list[Any]) -> set[str]:
    """Normalized place names from profile visited entries."""
    names: set[str] = set()
    for place in visited_places:
        if not isinstance(place, dict):
            continue
        name = normalize_place_text(str(place.get("name") or ""))
        if name:
            names.add(name)
    return names


def place_matches_visited_name(place: dict[str, Any], visited_names: set[str]) -> bool:
    if not visited_names:
        return False
    name = normalize_place_text(str(place.get("name") or ""))
    if name and name in visited_names:
        return True
    key = ensure_place_key(place)
    key_name = key.split("|", 1)[0].strip()
    return bool(key_name and key_name in visited_names)


def filter_quality_places(
    places: list[dict[str, Any]],
    *,
    plan_date: date,
    max_comfortable_minutes: int,
    profile_visited_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Drop closed / weekday-closed / profile-visited places, then trim for energy.

    Raises ApiError if fewer than 3 usable places remain, or energy still exceeds
    after trimming while keeping at least 3 stops.
    """
    visited_names = profile_visited_names or set()
    kept: list[dict[str, Any]] = []
    for place in places:
        enriched = {**place, "place_key": ensure_place_key(place)}
        if is_permanently_closed(enriched):
            continue
        if is_closed_on_date(enriched, plan_date):
            continue
        if place_matches_visited_name(enriched, visited_names):
            continue
        kept.append(enriched)

    if len(kept) < 3:
        raise ApiError(
            422,
            "fewer than 3 open places remain after closed/visited filters; "
            "retry plan-next-day",
            code="quality_empty",
        )

    # Drop from the end until under the energy warning threshold (keep ≥3).
    while len(kept) > 3 and day_total_minutes(kept) > max_comfortable_minutes:
        kept.pop()

    if day_total_minutes(kept) > max_comfortable_minutes:
        raise ApiError(
            422,
            f"day plan exceeds energy warning threshold "
            f"({day_total_minutes(kept)} > {max_comfortable_minutes} minutes)",
            code="energy_overload",
        )
    return kept


def validate_suggested_place(
    place: dict[str, Any],
    *,
    existing_places: list[dict[str, Any]],
    plan_date: date,
    max_comfortable_minutes: int,
    already_visited_keys: set[str] | None = None,
    profile_visited_names: set[str] | None = None,
) -> dict[str, Any]:
    """Validate one Place before appending it to an existing day.

    Raises ApiError on day-full, closed/visited conflicts, or energy overload.
    """
    if len(existing_places) >= 6:
        raise ApiError(422, "day already has the maximum of 6 places", code="day_full")

    enriched = {**place, "place_key": ensure_place_key(place)}
    if not str(enriched.get("name") or "").strip():
        raise ApiError(422, "suggested place missing name", code="invalid_place")

    minutes = _parse_nonneg_int(enriched.get("estimated_minutes"))
    if minutes < 1:
        raise ApiError(
            422,
            "suggested place must have estimated_minutes > 0",
            code="invalid_place",
        )
    enriched["estimated_minutes"] = minutes

    if is_permanently_closed(enriched):
        raise ApiError(422, "suggested place is permanently closed", code="place_closed")
    if is_closed_on_date(enriched, plan_date):
        raise ApiError(
            422,
            "suggested place is closed on this weekday",
            code="place_weekday_closed",
        )

    key = str(enriched["place_key"])
    existing_keys = {ensure_place_key(p) for p in existing_places}
    blocked = set(already_visited_keys or set()) | existing_keys
    if key in blocked:
        raise ApiError(
            422,
            "suggested place was already visited or is already on this day",
            code="place_duplicate",
        )

    visited_names = profile_visited_names or set()
    if place_matches_visited_name(enriched, visited_names):
        raise ApiError(
            422,
            "suggested place matches a profile visited place",
            code="place_duplicate",
        )

    order = len(existing_places) + 1
    enriched["order_in_day"] = order

    combined = [*existing_places, enriched]
    total = day_total_minutes(combined)
    if total > max_comfortable_minutes:
        raise ApiError(
            422,
            f"adding place would exceed energy warning threshold "
            f"({total} > {max_comfortable_minutes} minutes)",
            code="energy_overload",
        )
    return enriched
