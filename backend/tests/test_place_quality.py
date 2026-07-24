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
    kept = filter_quality_places(
        places,
        plan_date=MONDAY,
        max_comfortable_minutes=510,
    )
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
    kept = filter_quality_places(
        places,
        plan_date=MONDAY,
        max_comfortable_minutes=510,
        profile_visited_names={"senso-ji"},
    )
    assert [p["name"] for p in kept] == ["Park A", "Park B", "Park C"]


def test_trims_for_energy_or_rejects() -> None:
    places = [_open(f"Stop {i}", minutes=100) for i in range(5)]
    # 500 minutes total; cap 270 → trim to 3 stops of 300 still over → reject.
    with pytest.raises(ApiError) as exc:
        filter_quality_places(
            places,
            plan_date=MONDAY,
            max_comfortable_minutes=270,
        )
    assert exc.value.code == "energy_overload"

    # Cap 310 → trim trailing until 3×100 = 300 ≤ 310.
    kept = filter_quality_places(
        places,
        plan_date=MONDAY,
        max_comfortable_minutes=310,
    )
    assert len(kept) == 3
    assert sum(int(p["estimated_minutes"]) for p in kept) == 300


def test_energy_trim_preserves_food_meal_stops() -> None:
    places = [
        _open("Lunch", minutes=60, category="food", reason_to_visit="Lunch — ramen"),
        _open("Museum", minutes=120, category="museum"),
        _open("Park", minutes=120, category="park"),
        _open("Shop", minutes=120, category="shopping"),
        _open("Dinner", minutes=60, category="food", reason_to_visit="Dinner — sushi"),
    ]
    # 480 minutes; cap 250 → must drop non-food, keep both meals + one activity.
    kept = filter_quality_places(
        places,
        plan_date=MONDAY,
        max_comfortable_minutes=250,
    )
    names = [p["name"] for p in kept]
    assert "Lunch" in names
    assert "Dinner" in names
    assert len(kept) == 3
    assert sum(int(p["estimated_minutes"]) for p in kept) == 240


def test_energy_trim_can_drop_optional_food_snack() -> None:
    places = [
        _open("Lunch", minutes=80, category="food", reason_to_visit="Lunch —"),
        _open("Snack", minutes=80, category="food"),  # optional unlabeled
        _open("Cafe", minutes=80, category="food"),  # optional unlabeled
        _open("Museum", minutes=80, category="museum"),
        _open("Dinner", minutes=80, category="food", reason_to_visit="Dinner —"),
    ]
    # 400 minutes; cap 250 → drop museum then an optional food; keep lunch+dinner +1.
    kept = filter_quality_places(
        places,
        plan_date=MONDAY,
        max_comfortable_minutes=250,
    )
    names = [p["name"] for p in kept]
    assert "Lunch" in names
    assert "Dinner" in names
    assert "Museum" not in names
    assert len(kept) == 3
    assert sum(int(p["estimated_minutes"]) for p in kept) == 240
    # At least one optional food was dropped.
    assert ("Snack" in names) != ("Cafe" in names) or (
        "Snack" not in names and "Cafe" not in names
    )
    assert sum(1 for n in ("Snack", "Cafe") if n in names) <= 1


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


def test_energy_trim_reindexes_order_in_day() -> None:
    places = [
        _open("Lunch", minutes=60, category="food", reason_to_visit="Lunch —", order_in_day=1),
        _open("Museum", minutes=120, category="museum", order_in_day=2),
        _open("Park", minutes=120, category="park", order_in_day=3),
        _open("Dinner", minutes=60, category="food", reason_to_visit="Dinner —", order_in_day=4),
    ]
    kept = filter_quality_places(
        places,
        plan_date=MONDAY,
        max_comfortable_minutes=250,
    )
    assert [p["name"] for p in kept] == ["Lunch", "Museum", "Dinner"]
    assert [p["order_in_day"] for p in kept] == [1, 2, 3]


def test_validate_suggested_place_rejects_closed_and_overload() -> None:
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

    with pytest.raises(ApiError) as energy:
        validate_suggested_place(
            _open("Long", minutes=400),
            existing_places=existing,
            plan_date=MONDAY,
            max_comfortable_minutes=270,
        )
    assert energy.value.code == "energy_overload"

    ok = validate_suggested_place(
        _open("Extra", minutes=30),
        existing_places=existing,
        plan_date=MONDAY,
        max_comfortable_minutes=510,
    )
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
