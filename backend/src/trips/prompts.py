"""Crew-prompt text helpers: preference merging, meal rules, prior-day summaries.

Pure functions only — no DynamoDB/crew I/O. Per ADR 005, this module must never
import `trips.service.TripService`.
"""

from __future__ import annotations

from typing import Any

from db.place_keys import make_place_key


def _merge_preferences(trip_prefs: str, profile_prefs: str, interests: list[str]) -> str:
    parts: list[str] = []
    for chunk in (trip_prefs.strip(), profile_prefs.strip()):
        if chunk and chunk not in parts:
            parts.append(chunk)
    if interests:
        interest_line = "Interests: " + ", ".join(interests)
        if interest_line not in parts:
            parts.append(interest_line)
    return " | ".join(parts)


def _meal_guidance(*, include_breakfast: bool) -> str:
    """Hard meal requirements appended into crew preferences."""
    base = (
        "Meals: include lunch and dinner as itinerary Place stops — "
        "each is a named restaurant or cafe (category=food, real venue name + "
        "street address), with realistic meal timing in the day's order. "
        "Not a food district or abstract meal slot."
    )
    if include_breakfast:
        return (
            f"{base} Also include a named breakfast restaurant/cafe as a Place "
            "(suggest_include_breakfast=true)."
        )
    return f"{base} Skip breakfast unless the traveler preferences ask for it."


def prior_day_summary_line(
    *,
    day_index: int,
    theme: str,
    overnight_city: str,
    places: list[Any] | None = None,
) -> str:
    """One prior-days line: theme @ city, plus up to 8 place names for brand avoidance."""
    line = f"Day {day_index}: {theme} @ {overnight_city}".strip()
    if line.endswith("@"):
        line = line[:-1].strip()
    names: list[str] = []
    for place in places or []:
        if not isinstance(place, dict):
            continue
        name = str(place.get("name") or "").strip()
        if name and name not in names:
            names.append(name)
        if len(names) >= 8:
            break
    if names:
        return f"{line} — {', '.join(names)}"
    return line


def append_prior_day_summary_line(prior: str, line: str) -> str:
    prior = prior.strip()
    line = line.strip()
    if not line:
        return prior
    return f"{prior}\n{line}".strip() if prior else line


def rebuild_prior_days_summary(days: list[dict[str, Any]]) -> str:
    """One-line-per-day summary matching plan-next-day cursor updates.

    Includes place names so crews can avoid repeating the same brand/chain
    across cities (keys alone are easy to miss when city-suffixed).
    """
    lines: list[str] = []
    for day in sorted(days, key=lambda d: int(d.get("day_index") or 0)):
        index = int(day.get("day_index") or 0)
        if index < 1:
            continue
        lines.append(
            prior_day_summary_line(
                day_index=index,
                theme=str(day.get("theme") or f"Day {index}"),
                overnight_city=str(day.get("overnight_city") or ""),
                places=list(day.get("places") or []),
            )
        )
    return "\n".join(lines)


def visited_keys_from_days(days: list[dict[str, Any]]) -> list[str]:
    """Stable order of unique place_keys across remaining day plans."""
    keys: list[str] = []
    seen: set[str] = set()
    for day in sorted(days, key=lambda d: int(d.get("day_index") or 0)):
        for place in day.get("places") or []:
            if not isinstance(place, dict):
                continue
            key = str(place.get("place_key") or "").strip()
            if key and key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


def _profile_visited_keys(visited_places: list[Any]) -> list[str]:
    keys: list[str] = []
    for place in visited_places:
        if not isinstance(place, dict):
            continue
        name = str(place.get("name") or "").strip()
        if not name:
            continue
        city = str(place.get("city") or "").strip() or None
        keys.append(make_place_key(name, city))
    return keys
