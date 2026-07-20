"""Deterministic crew responses for offline tests and --skip-crew smoke."""

from __future__ import annotations

from typing import Any

from db.place_keys import make_place_key


class FakeCrewRunner:
    def propose_cities(self, inputs: dict[str, Any]) -> dict[str, Any]:
        day_count = int(inputs.get("day_count") or 7)
        destination = str(inputs.get("destination") or "Japan")
        destination_type = str(inputs.get("destination_type") or "country")

        if day_count == 1:
            cities = [
                {
                    "city": "Tokyo",
                    "country": destination,
                    "nights": 0,
                    "arrival_day_index": 1,
                    "departure_day_index": 1,
                    "reason": "Single-day visit",
                    "highlights": ["Senso-ji"],
                }
            ]
        else:
            tokyo_end = max(1, day_count // 2)
            cities = [
                {
                    "city": "Tokyo",
                    "country": destination,
                    "nights": tokyo_end - 1,
                    "arrival_day_index": 1,
                    "departure_day_index": tokyo_end,
                    "reason": "Capital culture and food",
                    "highlights": ["Senso-ji", "Shibuya"],
                },
                {
                    "city": "Kyoto",
                    "country": destination,
                    "nights": day_count - tokyo_end,
                    "arrival_day_index": tokyo_end + 1,
                    "departure_day_index": day_count,
                    "reason": "Temples and quieter pace",
                    "highlights": ["Fushimi Inari"],
                },
            ]

        return {
            "destination_type": destination_type,
            "cities": cities,
            "rationale": "Fake route for tests",
            "total_nights": sum(int(c["nights"]) for c in cities),
            "status": "proposed",
        }

    def plan_day(self, inputs: dict[str, Any]) -> dict[str, Any]:
        day_index = int(inputs.get("day_index") or 1)
        overnight = str(inputs.get("overnight_city") or "Tokyo")
        date_str = str(inputs.get("date") or "2026-09-01")
        places = []
        for i in range(1, 4):
            name = f"{overnight} Spot {i} D{day_index}"
            address = f"{i} Main St, {overnight}"
            places.append(
                {
                    "name": name,
                    "address": address,
                    "category": "other",
                    "reason_to_visit": "Test stop",
                    "details": "Synthetic place for FakeCrewRunner",
                    "estimated_minutes": 60,
                    "has_bathroom": None,
                    "order_in_day": i,
                    "place_key": make_place_key(name, address),
                }
            )
        return {
            "day_index": day_index,
            "date": date_str,
            "theme": f"Day {day_index} in {overnight}",
            "summary": "Fake day plan",
            "overnight_city": overnight,
            "places": places,
        }
