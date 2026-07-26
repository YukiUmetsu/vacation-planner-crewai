"""Remap planned DAY rows onto a newly confirmed city route.

Days are matched by overnight city (FIFO within each city). Calendar
``day_index`` / ``date`` / Dynamo keys change; places and theme are kept.
Slots with no matching prior plan stay empty for plan-next-day.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import date
from typing import Any

from shared.dates import date_for_day_index


_STRIP_KEYS = frozenset(
    {
        "pk",
        "sk",
        "gsi1pk",
        "gsi1sk",
        "entity_type",
        "trip_id",
        "updated_at",
        "remap_route_fp",
    }
)


def norm_overnight_city(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def route_remap_fingerprint(route: dict[str, Any]) -> str:
    """Stable fingerprint of city windows used to validate staging resume."""
    cities = []
    for stop in route.get("cities") or []:
        if not isinstance(stop, dict):
            continue
        cities.append(
            [
                str(stop.get("city") or "").strip(),
                int(stop.get("nights") or 0),
                int(stop.get("arrival_day_index") or 0),
                int(stop.get("departure_day_index") or 0),
            ]
        )
    return json.dumps(cities, separators=(",", ":"), ensure_ascii=False)


def overnight_schedule(
    route: dict[str, Any], *, day_count: int, destination: str
) -> list[str]:
    """Overnight city name for each day index 1..day_count (route must cover all)."""
    cities = list(route.get("cities") or [])
    schedule: list[str] = []
    for day_index in range(1, day_count + 1):
        name = destination
        for stop in cities:
            arrival = int(stop.get("arrival_day_index") or 0)
            departure = int(stop.get("departure_day_index") or 0)
            if arrival <= day_index <= departure:
                name = str(stop.get("city") or destination)
                break
        schedule.append(name)
    return schedule


def remap_day_plans(
    existing_days: list[dict[str, Any]],
    *,
    route: dict[str, Any],
    day_count: int,
    start_date: date,
    destination: str,
) -> list[dict[str, Any]]:
    """
    Build DAY payloads for the new route windows.

    For each new calendar day, take the next unused prior day whose
    ``overnight_city`` matches (case/whitespace-insensitive). Extra prior
    days for a city (nights shrunk) are dropped; new slots without a match
    are omitted (caller leaves gaps).
    """
    pools: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    for day in sorted(existing_days, key=lambda d: int(d.get("day_index") or 0)):
        key = norm_overnight_city(day.get("overnight_city"))
        if key:
            pools[key].append(day)

    out: list[dict[str, Any]] = []
    for day_index, overnight in enumerate(
        overnight_schedule(route, day_count=day_count, destination=destination),
        start=1,
    ):
        key = norm_overnight_city(overnight)
        if not key or not pools.get(key):
            continue
        old = pools[key].popleft()
        payload = {k: v for k, v in old.items() if k not in _STRIP_KEYS}
        payload["day_index"] = day_index
        payload["date"] = date_for_day_index(start_date, day_index).isoformat()
        payload["overnight_city"] = overnight
        out.append(payload)
    return out
