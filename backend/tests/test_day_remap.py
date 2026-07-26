"""Unit tests for day↔route remapping."""

from __future__ import annotations

from datetime import date

from trips.day_remap import (
    overnight_schedule,
    remap_day_plans,
    route_remap_fingerprint,
)


def test_remap_moves_city_block_to_new_indexes() -> None:
    route = {
        "cities": [
            {
                "city": "Kyoto",
                "nights": 2,
                "arrival_day_index": 1,
                "departure_day_index": 3,
            },
            {
                "city": "Tokyo",
                "nights": 3,
                "arrival_day_index": 4,
                "departure_day_index": 7,
            },
        ]
    }
    existing = [
        {
            "day_index": 1,
            "date": "2026-09-01",
            "overnight_city": "Tokyo",
            "theme": "Neon",
            "places": [{"place_key": "a|x", "name": "A"}],
        },
        {
            "day_index": 2,
            "date": "2026-09-02",
            "overnight_city": "Tokyo",
            "theme": "Parks",
            "places": [{"place_key": "b|y", "name": "B"}],
        },
    ]

    out = remap_day_plans(
        existing,
        route=route,
        day_count=7,
        start_date=date(2026, 9, 1),
        destination="Japan",
    )
    assert [d["day_index"] for d in out] == [4, 5]
    assert [d["overnight_city"] for d in out] == ["Tokyo", "Tokyo"]
    assert out[0]["places"][0]["name"] == "A"
    assert out[0]["date"] == "2026-09-04"
    assert out[1]["date"] == "2026-09-05"


def test_remap_drops_extra_days_when_nights_shrink() -> None:
    route = {
        "cities": [
            {
                "city": "Tokyo",
                "nights": 1,
                "arrival_day_index": 1,
                "departure_day_index": 2,
            },
            {
                "city": "Kyoto",
                "nights": 4,
                "arrival_day_index": 3,
                "departure_day_index": 7,
            },
        ]
    }
    existing = [
        {"day_index": 1, "overnight_city": "Tokyo", "places": [{"name": "1"}]},
        {"day_index": 2, "overnight_city": "Tokyo", "places": [{"name": "2"}]},
        {"day_index": 3, "overnight_city": "Tokyo", "places": [{"name": "3"}]},
    ]
    out = remap_day_plans(
        existing,
        route=route,
        day_count=7,
        start_date=date(2026, 9, 1),
        destination="Japan",
    )
    # Tokyo window is days 1–2 → only two slots; third Tokyo plan dropped.
    assert len(out) == 2
    assert [d["places"][0]["name"] for d in out] == ["1", "2"]


def test_overnight_schedule_covers_window() -> None:
    route = {
        "cities": [
            {
                "city": "Tokyo",
                "arrival_day_index": 1,
                "departure_day_index": 3,
            },
            {
                "city": "Osaka",
                "arrival_day_index": 4,
                "departure_day_index": 5,
            },
        ]
    }
    assert overnight_schedule(route, day_count=5, destination="Japan") == [
        "Tokyo",
        "Tokyo",
        "Tokyo",
        "Osaka",
        "Osaka",
    ]


def test_route_remap_fingerprint_changes_with_order() -> None:
    a = {
        "cities": [
            {"city": "Tokyo", "nights": 3, "arrival_day_index": 1, "departure_day_index": 3},
            {"city": "Kyoto", "nights": 3, "arrival_day_index": 4, "departure_day_index": 7},
        ]
    }
    b = {
        "cities": [
            {"city": "Kyoto", "nights": 3, "arrival_day_index": 1, "departure_day_index": 3},
            {"city": "Tokyo", "nights": 3, "arrival_day_index": 4, "departure_day_index": 7},
        ]
    }
    assert route_remap_fingerprint(a) != route_remap_fingerprint(b)
    assert route_remap_fingerprint(a) == route_remap_fingerprint(a)
