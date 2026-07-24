"""Tests for post-crew place quality filters."""

from __future__ import annotations

from datetime import date

import pytest

from http_utils import ApiError
from services.place_quality import filter_quality_places


MONDAY = date(2026, 9, 7)  # weekday 0


def _open(name: str, minutes: int = 60, **extra: object) -> dict:
    return {
        "name": name,
        "place_key": f"{name.lower()}|x",
        "estimated_minutes": minutes,
        "operational_status": "open",
        **extra,
    }


def test_drops_permanently_closed_and_weekday_closed() -> None:
    places = [
        _open("Closed Cafe", operational_status="closed"),
        _open("Monday Museum", closed_weekdays=[0]),
        _open("Park A"),
        _open("Park B"),
        _open("Park C"),
        _open("Park D"),
    ]
    kept, soft = filter_quality_places(
        places,
        plan_date=MONDAY,
        max_comfortable_minutes=510,
    )
    assert soft == []
    assert [p["name"] for p in kept] == ["Park A", "Park B", "Park C", "Park D"]


def test_rejects_when_fewer_than_three_open() -> None:
    places = [
        _open("Closed Cafe", operational_status="closed"),
        _open("Monday Museum", closed_weekdays=[0]),
        _open("Park"),
    ]
    with pytest.raises(ApiError) as exc:
        filter_quality_places(
            places,
            plan_date=MONDAY,
            max_comfortable_minutes=510,
        )
    assert exc.value.code == "quality_empty"


def test_drops_profile_visited_by_name() -> None:
    places = [
        {
            "name": "Senso-ji",
            "address": "1 Asakusa",
            "place_key": "senso-ji|1 asakusa",
            "estimated_minutes": 60,
            "operational_status": "open",
        },
        _open("Park A"),
        _open("Park B"),
        _open("Park C"),
    ]
    kept, soft = filter_quality_places(
        places,
        plan_date=MONDAY,
        max_comfortable_minutes=510,
        profile_visited_names={"senso-ji"},
    )
    assert soft == []
    assert [p["name"] for p in kept] == ["Park A", "Park B", "Park C"]


def test_energy_overload_warns_without_trimming() -> None:
    places = [_open(f"Stop {i}", minutes=100) for i in range(5)]
    kept, soft = filter_quality_places(
        places,
        plan_date=MONDAY,
        max_comfortable_minutes=270,
    )
    assert len(kept) == 5
    assert soft == ["energy_overload"]
    assert sum(int(p["estimated_minutes"]) for p in kept) == 500

    under, soft_under = filter_quality_places(
        places[:3],
        plan_date=MONDAY,
        max_comfortable_minutes=310,
    )
    assert soft_under == []
    assert len(under) == 3


def test_require_meal_stops_lunch_and_dinner() -> None:
    from services.place_quality import infer_meal_role, require_meal_stops

    require_meal_stops(
        [
            _open("Lunch", category="food", reason_to_visit="Lunch —"),
            _open("Park", category="park"),
            _open("Dinner", category="food", reason_to_visit="Dinner —"),
        ]
    )

    require_meal_stops(
        [
            _open("Cafe A", category="food"),
            _open("Park", category="park"),
            _open("Cafe B", category="food"),
        ]
    )

    # Labeled lunch + unlabeled food covers dinner.
    require_meal_stops(
        [
            _open("Ramen", category="food", reason_to_visit="Lunch — tonkotsu"),
            _open("Park", category="park"),
            _open("Izakaya", category="food"),
        ]
    )

    with pytest.raises(ApiError) as exc:
        require_meal_stops(
            [
                _open("Park A", category="park"),
                _open("Park B", category="park"),
                _open("Museum", category="museum"),
            ]
        )
    assert exc.value.code == "missing_meals"

    with pytest.raises(ApiError) as labeled:
        require_meal_stops(
            [
                _open("Lunch only", category="food", reason_to_visit="Lunch —"),
                _open("Park", category="park"),
                _open("Museum", category="museum"),
            ]
        )
    assert labeled.value.code == "missing_meals"

    with pytest.raises(ApiError) as breakfast:
        require_meal_stops(
            [
                _open("Lunch", category="food", reason_to_visit="Lunch —"),
                _open("Dinner", category="food", reason_to_visit="Dinner —"),
                _open("Park", category="park"),
            ],
            include_breakfast=True,
        )
    assert breakfast.value.code == "missing_meals"

    assert (
        infer_meal_role(
            {
                "reason_to_visit": "Lunch — try their brunch set",
                "name": "Cafe",
                "category": "food",
            }
        )
        == "lunch"
    )


def test_filter_reindexes_order_in_day() -> None:
    places = [
        _open("Lunch", minutes=60, category="food", reason_to_visit="Lunch —", order_in_day=9),
        _open("Museum", minutes=120, category="museum", order_in_day=2),
        _open("Dinner", minutes=60, category="food", reason_to_visit="Dinner —", order_in_day=1),
    ]
    kept, soft = filter_quality_places(
        places,
        plan_date=MONDAY,
        max_comfortable_minutes=510,
    )
    assert soft == []
    assert [p["name"] for p in kept] == ["Lunch", "Museum", "Dinner"]
    assert [p["order_in_day"] for p in kept] == [1, 2, 3]


def test_validate_suggested_place_rejects_closed_and_warns_overload() -> None:
    from services.place_quality import validate_suggested_place

    existing = [_open("A"), _open("B"), _open("C")]
    with pytest.raises(ApiError) as closed:
        validate_suggested_place(
            _open("Bad", operational_status="closed"),
            existing_places=existing,
            plan_date=MONDAY,
            max_comfortable_minutes=510,
        )
    assert closed.value.code == "place_closed"

    place, soft = validate_suggested_place(
        _open("Long", minutes=400),
        existing_places=existing,
        plan_date=MONDAY,
        max_comfortable_minutes=270,
    )
    assert place["name"] == "Long"
    assert soft == ["energy_overload"]

    ok, soft_ok = validate_suggested_place(
        _open("Extra", minutes=30),
        existing_places=existing,
        plan_date=MONDAY,
        max_comfortable_minutes=510,
    )
    assert soft_ok == []
    assert ok["order_in_day"] == 4
    assert ok["place_key"]

    with pytest.raises(ApiError) as zero_mins:
        validate_suggested_place(
            {**_open("Zero"), "estimated_minutes": 0},
            existing_places=existing,
            plan_date=MONDAY,
            max_comfortable_minutes=510,
        )
    assert zero_mins.value.code == "invalid_place"
