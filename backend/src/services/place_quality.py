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


def is_food_place(place: dict[str, Any]) -> bool:
    return str(place.get("category") or "").strip().lower() == "food"


_MEAL_PREFIXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "breakfast",
        (
            "breakfast —",
            "breakfast -",
            "breakfast:",
            "breakfast –",
            "brunch —",
            "brunch -",
            "brunch:",
            "brunch –",
        ),
    ),
    (
        "lunch",
        ("lunch —", "lunch -", "lunch:", "lunch –", "midday meal"),
    ),
    (
        "dinner",
        (
            "dinner —",
            "dinner -",
            "dinner:",
            "dinner –",
            "supper —",
            "supper -",
            "supper:",
            "evening meal",
        ),
    ),
)


def infer_meal_role(place: dict[str, Any]) -> str | None:
    """Return breakfast|lunch|dinner when the stop is labeled as that meal.

    Prefer ``reason_to_visit`` prefixes (``Lunch —`` …) so incidental words like
    "brunch" inside a lunch blurb do not steal the role. Fall back to whole-field
    keywords only when no prefix matches.
    """
    reason = str(place.get("reason_to_visit") or "").strip().lower()
    if reason:
        for role, prefixes in _MEAL_PREFIXES:
            if any(reason.startswith(prefix) for prefix in prefixes):
                return role

    blob = " ".join(
        str(place.get(field) or "")
        for field in ("reason_to_visit", "name", "details", "notes")
    ).lower()
    # Order: lunch/dinner before brunch/breakfast so "lunch … brunch set" stays lunch.
    if "lunch" in blob or "midday meal" in blob:
        return "lunch"
    if "dinner" in blob or "supper" in blob or "evening meal" in blob:
        return "dinner"
    if "breakfast" in blob or "brunch" in blob:
        return "breakfast"
    return None


def require_meal_stops(
    places: list[dict[str, Any]],
    *,
    include_breakfast: bool = False,
) -> None:
    """Raise if the day is missing required meal food stops.

    Lunch and dinner are always required (``category=food``). Breakfast is
    required when ``include_breakfast`` is true.

    Labeled roles (``Lunch —`` / ``Dinner —`` / …) count first; each remaining
    unlabeled food stop may cover one missing required role so a labeled lunch
    plus an unlabeled cafe still satisfies dinner.
    """
    food = [p for p in places if is_food_place(p)]
    roles = [infer_meal_role(p) for p in food]
    present = {role for role in roles if role is not None}
    unlabeled = sum(1 for role in roles if role is None)
    required = (
        ["breakfast", "lunch", "dinner"]
        if include_breakfast
        else ["lunch", "dinner"]
    )

    missing: list[str] = []
    for meal in required:
        if meal in present:
            continue
        if unlabeled > 0:
            unlabeled -= 1
            continue
        missing.append(meal)

    if not missing:
        return

    raise ApiError(
        422,
        "day plan must include "
        + " and ".join(required)
        + f" as category=food stops (missing: {', '.join(missing)})",
        code="missing_meals",
    )


def _protected_meal_indices(
    places: list[dict[str, Any]],
    *,
    include_breakfast: bool = False,
) -> set[int]:
    """Indices of food stops that cover required lunch/dinner (/breakfast)."""
    required = (
        ["breakfast", "lunch", "dinner"]
        if include_breakfast
        else ["lunch", "dinner"]
    )
    food_indices = [i for i, place in enumerate(places) if is_food_place(place)]
    assigned: set[int] = set()
    remaining = list(required)

    for meal in list(remaining):
        for index in food_indices:
            if index in assigned:
                continue
            if infer_meal_role(places[index]) == meal:
                assigned.add(index)
                remaining.remove(meal)
                break

    for _meal in list(remaining):
        for index in food_indices:
            if index in assigned:
                continue
            if infer_meal_role(places[index]) is None:
                assigned.add(index)
                remaining.remove(_meal)
                break

    return assigned


def _last_droppable_index(
    places: list[dict[str, Any]],
    *,
    protected: set[int],
) -> int | None:
    """Drop non-protected stops first; optional food may be dropped after activities."""
    for index in range(len(places) - 1, -1, -1):
        if index not in protected and not is_food_place(places[index]):
            return index
    for index in range(len(places) - 1, -1, -1):
        if index not in protected:
            return index
    return None


def _reindex_order_in_day(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for index, place in enumerate(places, start=1):
        place["order_in_day"] = index
    return places


def filter_quality_places(
    places: list[dict[str, Any]],
    *,
    plan_date: date,
    max_comfortable_minutes: int,
    profile_visited_names: set[str] | None = None,
    include_breakfast: bool = False,
) -> list[dict[str, Any]]:
    """Drop closed / weekday-closed / profile-visited places, then trim for energy.

    Energy trim drops non-required stops first (activities, then optional food)
    so required lunch/dinner (/breakfast) survive. Raises ApiError if fewer than
    3 usable places remain, or energy still exceeds after trimming while keeping
    at least 3 stops.
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

    while len(kept) > 3 and day_total_minutes(kept) > max_comfortable_minutes:
        protected = _protected_meal_indices(
            kept, include_breakfast=include_breakfast
        )
        drop_at = _last_droppable_index(kept, protected=protected)
        if drop_at is None:
            break
        kept.pop(drop_at)

    if day_total_minutes(kept) > max_comfortable_minutes:
        raise ApiError(
            422,
            f"day plan exceeds energy warning threshold "
            f"({day_total_minutes(kept)} > {max_comfortable_minutes} minutes)",
            code="energy_overload",
        )
    return _reindex_order_in_day(kept)


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
