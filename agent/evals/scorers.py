"""Scoring hooks for offline evals.

Return a list of human-readable failure strings; empty list means pass.
"""

from __future__ import annotations

from typing import Any

from evals.case import EvalCase


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

    if len(keys) != len(set(keys)):
        failures.append("place_key values must be unique within the day")

    already = case.inputs.get("already_visited") or []
    if isinstance(already, list):
        blocked = {str(k) for k in already}
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


def score_output(output: dict[str, Any], case: EvalCase) -> list[str]:
    if case.crew == "day_plan":
        return score_day_plan(output, case)
    return score_city_route(output, case)
