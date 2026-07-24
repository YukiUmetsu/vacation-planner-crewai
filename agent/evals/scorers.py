"""Scoring hooks for offline evals.

Return a list of human-readable failure strings; empty list means pass.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from evals.case import EvalCase

# Keep in sync with docs/PLANNING_QUALITY.md and backend/services/energy.py
_MAX_MINUTES_BY_ENERGY: dict[int, int] = {
    1: 270,
    2: 390,
    3: 510,
    4: 720,
    5: 840,
}


def _parse_nonneg_int(value: Any, *, label: str) -> tuple[int | None, str | None]:
    """Parse a non-negative int; on failure return ``(None, error message)``."""
    if value is None or value == "":
        return 0, None
    if isinstance(value, bool):
        return None, f"{label} must be an integer, got {value!r}"
    if isinstance(value, int):
        if value < 0:
            return None, f"{label} must be >= 0, got {value}"
        return value, None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value), None
    if isinstance(value, str) and value.strip():
        try:
            parsed = int(value.strip())
        except ValueError:
            return None, f"{label} must be an integer, got {value!r}"
        if parsed < 0:
            return None, f"{label} must be >= 0, got {parsed}"
        return parsed, None
    return None, f"{label} must be an integer, got {value!r}"


def _resolve_max_minutes(case: EvalCase) -> int | None:
    expected = case.expected
    raw = expected.get("max_total_minutes")
    if raw is not None:
        parsed, err = _parse_nonneg_int(raw, label="expected.max_total_minutes")
        return None if err else parsed
    energy = case.inputs.get("energy_level")
    if energy is None or energy == "":
        return None
    level, err = _parse_nonneg_int(energy, label="energy_level")
    if err or level is None or level not in _MAX_MINUTES_BY_ENERGY:
        return None
    return _MAX_MINUTES_BY_ENERGY[level]


def _day_total_minutes(places: list[Any]) -> int:
    total = 0
    for place in places:
        if not isinstance(place, dict):
            continue
        mins, _ = _parse_nonneg_int(place.get("estimated_minutes"), label="estimated_minutes")
        travel, _ = _parse_nonneg_int(
            place.get("travel_minutes_from_previous"),
            label="travel_minutes_from_previous",
        )
        total += mins or 0
        total += travel or 0
    return total


def _parse_plan_date(case: EvalCase) -> date | None:
    raw = case.inputs.get("date") or case.expected.get("date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(str(raw)).date()
        except ValueError:
            return None


def _closed_weekdays(place: dict[str, Any]) -> list[int]:
    raw = place.get("closed_weekdays") or []
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for item in raw:
        try:
            day = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= day <= 6 and day not in out:
            out.append(day)
    return out


def _as_key_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _as_lower_token_list(value: Any) -> list[str]:
    """Normalize list or comma-separated string into lowercased tokens."""
    return [token.lower() for token in _as_key_list(value)]


def score_day_plan(output: dict[str, Any], case: EvalCase) -> list[str]:
    """Return failure messages for a ``day_plan`` crew output."""
    failures: list[str] = []
    expected = case.expected
    places = output.get("places")
    if not isinstance(places, list):
        return ["day_plan.places must be a list"]

    min_places = expected.get("min_places")
    max_places = expected.get("max_places")
    if isinstance(min_places, int) and len(places) < min_places:
        failures.append(f"expected at least {min_places} places, got {len(places)}")
    if isinstance(max_places, int) and len(places) > max_places:
        failures.append(f"expected at most {max_places} places, got {len(places)}")

    overnight = output.get("overnight_city")
    want_city = case.inputs.get("overnight_city")
    if want_city and overnight != want_city:
        failures.append(f"overnight_city {overnight!r} != {want_city!r}")

    max_minutes = _resolve_max_minutes(case)
    if max_minutes is not None:
        total = _day_total_minutes(places)
        if total > max_minutes:
            failures.append(
                f"day total {total} minutes exceeds energy warning threshold {max_minutes}"
            )

    plan_date = _parse_plan_date(case)
    weekday = plan_date.weekday() if plan_date else None

    keys: list[str] = []
    for i, place in enumerate(places):
        if not isinstance(place, dict):
            failures.append(f"places[{i}] must be an object")
            continue
        if not str(place.get("name") or "").strip():
            failures.append(f"places[{i}] missing name")
        key = str(place.get("place_key") or "").strip()
        if not key:
            failures.append(f"places[{i}] missing place_key")
        else:
            keys.append(key)

        status = str(place.get("operational_status") or "unknown").strip().lower()
        if status == "closed":
            failures.append(
                f"places[{i}] ({place.get('name')!r}) is permanently closed"
            )
        closed_days = _closed_weekdays(place)
        if weekday is not None and weekday in closed_days:
            failures.append(
                f"places[{i}] ({place.get('name')!r}) is closed on weekday {weekday} "
                f"for date {plan_date.isoformat()}"
            )

    if len(keys) != len(set(keys)):
        failures.append("place_key values must be unique within the day")

    food_count = sum(
        1
        for place in places
        if isinstance(place, dict)
        and str(place.get("category") or "").strip().lower() == "food"
    )
    # Full day plans (3+ stops) must include lunch + dinner food Places.
    if len(places) >= 3 and food_count < 2:
        failures.append(
            f"day plan must include lunch and dinner food stops "
            f"(got {food_count} category=food place(s))"
        )

    already = _as_key_list(case.inputs.get("already_visited"))
    if already:
        blocked = set(already)
        overlap = sorted(set(keys) & blocked)
        if overlap:
            failures.append(f"places reuse already_visited keys: {overlap}")

    forbidden = expected.get("forbidden_place_keys") or []
    if isinstance(forbidden, list):
        hit = sorted(set(keys) & {str(k) for k in forbidden})
        if hit:
            failures.append(f"places include forbidden_place_keys: {hit}")

    return failures


def score_city_route(output: dict[str, Any], case: EvalCase) -> list[str]:
    """Return failure messages for a ``city_route`` crew output."""
    failures: list[str] = []
    expected = case.expected
    cities = output.get("cities")
    if not isinstance(cities, list) or not cities:
        return ["city_route.cities must be a non-empty list"]

    min_cities = expected.get("min_cities")
    max_cities = expected.get("max_cities")
    if isinstance(min_cities, int) and len(cities) < min_cities:
        failures.append(f"expected at least {min_cities} cities, got {len(cities)}")
    if isinstance(max_cities, int) and len(cities) > max_cities:
        failures.append(f"expected at most {max_cities} cities, got {len(cities)}")

    nights_sum = 0
    nights_ok = True
    for i, stop in enumerate(cities):
        if not isinstance(stop, dict):
            failures.append(f"cities[{i}] must be an object")
            continue
        if not str(stop.get("city") or "").strip():
            failures.append(f"cities[{i}] missing city")
        nights, err = _parse_nonneg_int(stop.get("nights"), label=f"cities[{i}].nights")
        if err:
            failures.append(err)
            nights_ok = False
            continue
        assert nights is not None
        nights_sum += nights

    total = output.get("total_nights")
    if total is not None:
        total_nights, err = _parse_nonneg_int(total, label="total_nights")
        if err:
            failures.append(err)
        elif nights_ok and total_nights != nights_sum:
            failures.append(f"total_nights ({total_nights}) != sum of nights ({nights_sum})")

    return failures


def _existing_places_from_inputs(case: EvalCase) -> list[Any]:
    """Prefer scorer-only ``existing_places``; else parse production ``current_places_json``."""
    existing = case.inputs.get("existing_places")
    if isinstance(existing, list):
        return existing
    raw = case.inputs.get("current_places_json")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def score_suggest_place(output: dict[str, Any], case: EvalCase) -> list[str]:
    """Return failure messages for a ``suggest_place`` crew output (single Place)."""
    failures: list[str] = []
    place = output.get("place") if isinstance(output.get("place"), dict) else output
    if not isinstance(place, dict):
        return ["suggest_place output must be a Place object"]

    if not str(place.get("name") or "").strip():
        failures.append("place missing name")

    key = str(place.get("place_key") or "").strip()
    if not key:
        failures.append("place missing place_key")

    status = str(place.get("operational_status") or "unknown").strip().lower()
    if status == "closed":
        failures.append(f"place ({place.get('name')!r}) is permanently closed")

    plan_date = _parse_plan_date(case)
    weekday = plan_date.weekday() if plan_date else None
    closed_days = _closed_weekdays(place)
    if weekday is not None and weekday in closed_days:
        failures.append(
            f"place ({place.get('name')!r}) is closed on weekday {weekday} "
            f"for date {plan_date.isoformat()}"
        )

    already = _as_key_list(case.inputs.get("already_visited"))
    if key and already and key in set(already):
        failures.append(f"place reuses already_visited key: {key}")

    existing = _existing_places_from_inputs(case)
    if existing and key:
        existing_keys = {
            str(p.get("place_key") or "").strip()
            for p in existing
            if isinstance(p, dict) and str(p.get("place_key") or "").strip()
        }
        if key in existing_keys:
            failures.append(f"place duplicates existing day place_key: {key}")

    forbidden = case.expected.get("forbidden_place_keys") or []
    if isinstance(forbidden, list) and key and key in {str(k) for k in forbidden}:
        failures.append(f"place is in forbidden_place_keys: {key}")

    # Energy: place alone must fit remaining_minutes (or derived remaining).
    remaining_raw = case.inputs.get("remaining_minutes")
    remaining, rem_err = _parse_nonneg_int(remaining_raw, label="remaining_minutes")
    if rem_err:
        failures.append(rem_err)
    elif remaining is not None:
        place_mins = _day_total_minutes([place])
        if place_mins > remaining:
            failures.append(
                f"place total {place_mins} minutes exceeds remaining_minutes {remaining}"
            )

    # Optional: place + existing day must stay under energy cap.
    if existing:
        max_minutes = _resolve_max_minutes(case)
        if max_minutes is not None:
            combined = [p for p in existing if isinstance(p, dict)] + [place]
            total = _day_total_minutes(combined)
            if total > max_minutes:
                failures.append(
                    f"day total with suggestion {total} exceeds energy threshold {max_minutes}"
                )

    return failures


def collect_day_plan_metrics(
    output: dict[str, Any], case: EvalCase
) -> dict[str, float]:
    """Deterministic offline metrics (0–1 rates / scores) for a day_plan output."""
    places = output.get("places") if isinstance(output.get("places"), list) else []
    n = max(1, len(places))
    closed = 0
    dup = 0
    grounded = 0
    keys: list[str] = []
    for place in places:
        if not isinstance(place, dict):
            continue
        if str(place.get("operational_status") or "").lower() == "closed":
            closed += 1
        key = str(place.get("place_key") or "").strip()
        if key:
            if key in keys:
                dup += 1
            keys.append(key)
        if str(place.get("address") or "").strip() or str(place.get("maps_url") or "").strip():
            grounded += 1

    already = set(_as_key_list(case.inputs.get("already_visited")))
    exclusion_hits = len(set(keys) & already)

    interests = [
        str(i).strip().lower()
        for i in (case.expected.get("interests") or [])
        if str(i).strip()
    ]
    if not interests:
        raw_interests = case.inputs.get("interests")
        if isinstance(raw_interests, str):
            interests = [
                p.strip().lower() for p in raw_interests.split(",") if p.strip()
            ]
        elif isinstance(raw_interests, list):
            interests = [
                str(i).strip().lower() for i in raw_interests if str(i).strip()
            ]
    preference_hits = 0
    if interests:
        blob = " ".join(
            str(place.get(field) or "")
            for place in places
            if isinstance(place, dict)
            for field in ("name", "reason_to_visit", "details", "category")
        ).lower()
        preference_hits = sum(1 for interest in interests if interest in blob)
        preference_relevance_score = preference_hits / max(1, len(interests))
    else:
        preference_relevance_score = 1.0

    excluded_categories = _as_lower_token_list(
        case.expected.get("excluded_categories")
    )
    if not excluded_categories:
        excluded_categories = _as_lower_token_list(
            case.inputs.get("excluded_categories")
        )
    category_exclusion_hits = 0
    if excluded_categories:
        for place in places:
            if not isinstance(place, dict):
                continue
            cat = str(place.get("category") or "").strip().lower()
            if cat and cat in excluded_categories:
                category_exclusion_hits += 1

    max_minutes = _resolve_max_minutes(case)
    total = _day_total_minutes([p for p in places if isinstance(p, dict)])
    energy_overage = (
        1.0 if max_minutes is not None and total > max_minutes else 0.0
    )

    return {
        "preference_relevance_score": float(preference_relevance_score),
        "explicit_exclusion_violation_rate": float(
            exclusion_hits > 0 or category_exclusion_hits > 0
        ),
        "duplicate_rate": float(dup > 0),
        "closed_place_rate": closed / n,
        "energy_overage_rate": energy_overage,
        "grounding_rate": grounded / n,
    }


def score_output(output: dict[str, Any], case: EvalCase) -> list[str]:
    if case.crew == "day_plan":
        return score_day_plan(output, case)
    if case.crew == "suggest_place":
        return score_suggest_place(output, case)
    return score_city_route(output, case)
