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
