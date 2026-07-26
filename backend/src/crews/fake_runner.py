"""Deterministic crew responses for offline tests and --skip-crew smoke."""

from __future__ import annotations

import re
from typing import Any

from db.place_keys import make_place_key
from shared.route_windows import max_cities_for_trip

# Paced overnight bases (same order the Japan demo uses).
_CITY_POOL: list[tuple[str, str, list[str]]] = [
    ("Tokyo", "Capital culture and food", ["Senso-ji", "Shibuya"]),
    ("Kyoto", "Temples and quieter pace", ["Fushimi Inari"]),
    ("Osaka", "Street food and nightlife", ["Dotonbori"]),
    ("Hiroshima", "History and nearby islands", ["Peace Park"]),
    ("Nara", "Parks and early capitals", ["Todai-ji"]),
]


def _split_nights(total_nights: int, n_cities: int) -> list[int]:
    """Distribute overnight nights across cities (sum exact; zeros allowed)."""
    if n_cities <= 0:
        return []
    if total_nights <= 0:
        return [0] * n_cities
    base, rem = divmod(total_nights, n_cities)
    return [base + (1 if i < rem else 0) for i in range(n_cities)]


def _cities_from_nights(
    *,
    destination: str,
    day_count: int,
    night_parts: list[int],
) -> list[dict[str, Any]]:
    """Build contiguous day windows; last stop is pinned through ``day_count``."""
    cities: list[dict[str, Any]] = []
    day = 1
    for i, nights in enumerate(night_parts):
        name, reason, highlights = _CITY_POOL[i % len(_CITY_POOL)]
        is_last = i == len(night_parts) - 1
        arrival = day
        if is_last:
            departure = day_count
            nights = max(0, departure - arrival)
        elif nights <= 0:
            departure = arrival
            nights = 0
        else:
            # Non-last: nights calendar days in the stop (matches frontend recompute).
            departure = arrival + nights - 1
        cities.append(
            {
                "city": name,
                "country": destination,
                "nights": nights,
                "arrival_day_index": arrival,
                "departure_day_index": departure,
                "reason": reason,
                "highlights": list(highlights),
            }
        )
        day = departure + 1
    return cities


class FakeCrewRunner:
    def __init__(self) -> None:
        self.last_plan_day_inputs: dict[str, Any] | None = None
        self.last_suggest_place_inputs: dict[str, Any] | None = None
        self.last_suggest_city_inputs: dict[str, Any] | None = None

    def propose_cities(self, inputs: dict[str, Any]) -> dict[str, Any]:
        day_count = max(1, int(inputs.get("day_count") or 7))
        destination = str(inputs.get("destination") or "Japan")
        destination_type = str(inputs.get("destination_type") or "country")

        n_cities = max_cities_for_trip(day_count=day_count)
        total_nights = max(0, day_count - 1)
        night_parts = _split_nights(total_nights, n_cities)
        cities = _cities_from_nights(
            destination=destination,
            day_count=day_count,
            night_parts=night_parts,
        )

        return {
            "destination_type": destination_type,
            "cities": cities,
            "rationale": f"Fake paced route ({n_cities} cities for {day_count} days)",
            "total_nights": sum(int(c["nights"]) for c in cities),
            "status": "proposed",
        }

    def plan_day(self, inputs: dict[str, Any]) -> dict[str, Any]:
        self.last_plan_day_inputs = dict(inputs)
        day_index = int(inputs.get("day_index") or 1)
        overnight = str(inputs.get("overnight_city") or "Tokyo")
        date_str = str(inputs.get("date") or "2026-09-01")
        prefs = str(inputs.get("preferences") or "").lower()
        include_breakfast = (
            str(inputs.get("include_breakfast") or "").lower() == "true"
            or "include breakfast" in prefs
            or "suggest_include_breakfast=true" in prefs
        )
        places: list[dict[str, Any]] = []
        order = 1
        if include_breakfast:
            name = f"{overnight} Breakfast D{day_index}"
            address = f"1 Morning St, {overnight}"
            places.append(
                {
                    "name": name,
                    "address": address,
                    "category": "food",
                    "reason_to_visit": "Breakfast — cafe",
                    "details": "Synthetic breakfast for FakeCrewRunner",
                    "estimated_minutes": 45,
                    "order_in_day": order,
                    "has_bathroom": None,
                    "place_key": make_place_key(name, address),
                }
            )
            order += 1
        lunch_name = f"{overnight} Lunch D{day_index}"
        lunch_address = f"2 Noon St, {overnight}"
        places.append(
            {
                "name": lunch_name,
                "address": lunch_address,
                "category": "food",
                "reason_to_visit": "Lunch — restaurant",
                "details": "Synthetic lunch for FakeCrewRunner",
                "estimated_minutes": 60,
                "order_in_day": order,
                "has_bathroom": None,
                "place_key": make_place_key(lunch_name, lunch_address),
            }
        )
        order += 1
        try:
            target = max(3, min(7, int(inputs.get("target_place_count") or 5)))
        except (TypeError, ValueError):
            target = 5
        # Non-meal activities between lunch and dinner (fill toward target).
        activity_slots = max(1, target - len(places) - 1)  # reserve dinner
        for i in range(activity_slots):
            spot_name = f"{overnight} Spot{i + 1} D{day_index}"
            spot_address = f"{5 + i} Main St, {overnight}"
            places.append(
                {
                    "name": spot_name,
                    "address": spot_address,
                    "category": "other",
                    "reason_to_visit": "Test stop",
                    "details": "Synthetic place for FakeCrewRunner",
                    "estimated_minutes": 45,
                    "order_in_day": order,
                    "has_bathroom": None,
                    "place_key": make_place_key(spot_name, spot_address),
                }
            )
            order += 1
        dinner_name = f"{overnight} Dinner D{day_index}"
        dinner_address = f"8 Evening St, {overnight}"
        places.append(
            {
                "name": dinner_name,
                "address": dinner_address,
                "category": "food",
                "reason_to_visit": "Dinner — restaurant",
                "details": "Synthetic dinner for FakeCrewRunner",
                "estimated_minutes": 60,
                "order_in_day": order,
                "has_bathroom": None,
                "place_key": make_place_key(dinner_name, dinner_address),
            }
        )
        return {
            "day_index": day_index,
            "date": date_str,
            "theme": f"Day in {overnight}",
            "overnight_city": overnight,
            "places": places,
        }

    def suggest_place(self, inputs: dict[str, Any]) -> dict[str, Any]:
        self.last_suggest_place_inputs = dict(inputs)
        overnight = str(inputs.get("overnight_city") or "Tokyo")
        day_index = str(inputs.get("day_index") or "1").strip() or "1"
        order = str(inputs.get("next_order_in_day") or "1").strip() or "1"
        prefer_non_food = str(inputs.get("prefer_non_food") or "").lower() == "true"
        hint = str(inputs.get("hint") or "").strip()
        hint_l = hint.casefold()
        prefs = str(inputs.get("preferences") or "").casefold()
        # Mirror BFF hint-category inference enough for unit tests.
        if any(
            token in hint_l or token in prefs
            for token in ("lunch", "dinner", "breakfast", "brunch", "category=food")
        ):
            name = f"{overnight} Lunch Spot D{day_index}-{order}"
            category = "food"
            reason = "Synthetic lunch stop"
        elif "park" in hint_l or "category=park" in prefs:
            name = f"{overnight} Park Spot D{day_index}-{order}"
            category = "park"
            reason = "Synthetic park stop"
        elif "bookstore" in hint_l or "shopping" in hint_l or "category=shopping" in prefs:
            name = f"{overnight} Shop Spot D{day_index}-{order}"
            category = "shopping"
            reason = "Synthetic shopping stop"
        elif prefer_non_food:
            name = f"{overnight} Extra Spot D{day_index}-{order}"
            category = "other"
            reason = "Extra non-food stop"
        else:
            name = f"{overnight} Extra Spot D{day_index}-{order}"
            category = "other"
            reason = "Extra fake stop"
        address = f"9 Side St #{order}, {overnight}"
        place = {
            "name": name,
            "address": address,
            "category": category,
            "reason_to_visit": reason,
            "details": "Synthetic suggest_place",
            "estimated_minutes": 45,
            "has_bathroom": None,
            "place_key": make_place_key(name, address),
        }
        return {"place": place}

    def suggest_city(self, inputs: dict[str, Any]) -> dict[str, Any]:
        self.last_suggest_city_inputs = dict(inputs)
        try:
            count = max(1, min(int(inputs.get("count") or 1), 3))
        except (TypeError, ValueError):
            count = 1
        banned_raw = str(inputs.get("already_listed_cities") or "")
        banned = {
            re.sub(r"\s+", " ", part.strip().casefold())
            for part in banned_raw.split(",")
            if part.strip()
        }
        hint = str(inputs.get("hint") or "").strip()
        destination = str(inputs.get("destination") or "Japan")
        pool = [
            ("Osaka", "Street food and nightlife", ["Dotonbori"]),
            ("Hiroshima", "History and nearby islands", ["Peace Park"]),
            ("Nara", "Parks and early capitals", ["Todai-ji"]),
            ("Hakone", "Onsen and mountain views", ["Lake Ashi"]),
            ("Kanazawa", "Gardens and crafts", ["Kenroku-en"]),
            ("Shanghai", "Bund skyline and food", ["The Bund"]),
            ("Hangzhou", "West Lake calm", ["West Lake"]),
            ("Chengdu", "Pandas and Sichuan food", ["Jinli"]),
        ]
        reason_suffix = f" ({hint})" if hint else ""
        candidates: list[dict[str, Any]] = []
        for name, reason, highlights in pool:
            key = re.sub(r"\s+", " ", name.casefold())
            if key in banned:
                continue
            candidates.append(
                {
                    "city": name,
                    "country": destination,
                    "reason": f"{reason}{reason_suffix}",
                    "highlights": list(highlights),
                    "recommended_nights": 1,
                }
            )
            if len(candidates) >= count:
                break
        if not candidates:
            # Deterministic unique fallback not in banned.
            for i in range(1, 10):
                name = f"Side Trip {i}"
                key = re.sub(r"\s+", " ", name.casefold())
                if key in banned:
                    continue
                candidates.append(
                    {
                        "city": name,
                        "country": destination,
                        "reason": f"Extra overnight base{reason_suffix}",
                        "highlights": [],
                        "recommended_nights": 1,
                    }
                )
                break
        return {"candidates": candidates}
