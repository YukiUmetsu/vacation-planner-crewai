"""Day-index gap healing and meal guidance for plan-next-day."""

from __future__ import annotations

from typing import Any

import pytest

from crews.fake_runner import FakeCrewRunner
from db import repository as repo
from http_utils import ApiError
from services.safety import NoopSafetyGate
from services.trip_service import (
    TripService,
    first_missing_day_index,
    resolve_plan_day_index,
    _meal_guidance,
)


USER = "test-user-meals"


@pytest.fixture()
def service(dynamodb_table: Any) -> TripService:
    return TripService(
        table=dynamodb_table,
        runner=FakeCrewRunner(),
        safety=NoopSafetyGate(),
    )


def _ready_trip(service: TripService) -> str:
    trip_id = service.create_trip(
        USER,
        {
            "origin": "Chicago",
            "destination": "Japan",
            "destination_type": "country",
            "start_date": "2026-09-01",
            "end_date": "2026-09-07",
            "preferences": "food",
        },
    )["trip"]["trip_id"]
    proposed = service.propose_cities(USER, trip_id)
    service.confirm_cities(
        USER,
        trip_id,
        {
            "destination_type": "country",
            "cities": proposed["route"]["cities"],
            "rationale": proposed["route"]["rationale"],
            "total_nights": proposed["route"]["total_nights"],
            "status": "confirmed",
        },
    )
    return trip_id


def test_first_missing_day_index_finds_gap() -> None:
    assert first_missing_day_index([], 3) == 1
    assert first_missing_day_index([{"day_index": 2}], 3) == 1
    assert first_missing_day_index([{"day_index": 1}, {"day_index": 2}], 3) == 3
    assert first_missing_day_index(
        [{"day_index": 1}, {"day_index": 2}, {"day_index": 3}], 3
    ) is None


def test_resolve_plan_day_index_heals_jumped_cursor() -> None:
    trip = {"day_count": 7, "next_day_index": 2}
    assert resolve_plan_day_index(trip=trip, days=[]) == 1
    assert resolve_plan_day_index(trip=trip, days=[{"day_index": 2}]) == 1


def test_meal_guidance_lunch_dinner_always() -> None:
    text = _meal_guidance(include_breakfast=False)
    assert "lunch" in text.lower()
    assert "dinner" in text.lower()
    assert "skip breakfast" in text.lower()
    with_b = _meal_guidance(include_breakfast=True)
    assert "breakfast" in with_b.lower()
    assert "suggest_include_breakfast=true" in with_b


def test_meal_guidance_survives_preferences_slim() -> None:
    """Preferences are truncated from the end — meal rules must be prepended."""
    from services.crew_context_budget import slim_crew_inputs

    meal = _meal_guidance(include_breakfast=False)
    huge_tail = "x" * 20_000
    prefs = f"{meal} | {huge_tail}"
    slimmed = slim_crew_inputs(
        {
            "preferences": prefs,
            "include_breakfast": "false",
            "already_visited": "",
            "prior_days_summary": "",
            "city_route_json": "",
        },
        max_chars=2_000,
    )
    out = str(slimmed.get("preferences") or "")
    assert out.startswith("Meals:")
    assert "lunch" in out.lower() and "dinner" in out.lower()


def test_plan_next_day_heals_missing_day_one(
    service: TripService, dynamodb_table: Any
) -> None:
    """If cursor advanced without DAY#01, the next plan fills day 1."""
    trip_id = _ready_trip(service)
    repo.update_trip(
        user_sub=USER,
        trip_id=trip_id,
        updates={"next_day_index": 2, "status": "planning"},
        table=dynamodb_table,
    )
    planned = service.plan_next_day(USER, trip_id)
    assert planned["day"]["day_index"] == 1
    food = [
        p
        for p in planned["day"]["places"]
        if str(p.get("category") or "") == "food"
    ]
    assert len(food) >= 2
    assert any("Lunch" in str(p.get("name") or "") for p in food)
    assert any("Dinner" in str(p.get("name") or "") for p in food)


def test_plan_next_day_includes_breakfast_when_profile_asks(
    service: TripService, dynamodb_table: Any
) -> None:
    from services.profile_service import ProfileService

    ProfileService(table=dynamodb_table, safety=NoopSafetyGate()).put_profile(
        USER,
        {
            "display_name": "Traveler",
            "preferences": "",
            "energy_level": 3,
            "interests": [],
            "visited_places": [],
            "suggest_include_breakfast": True,
        },
    )
    trip_id = _ready_trip(service)
    planned = service.plan_next_day(USER, trip_id)
    names = [str(p.get("name") or "") for p in planned["day"]["places"]]
    assert any("Breakfast" in n for n in names)
    assert any("Lunch" in n for n in names)
    assert any("Dinner" in n for n in names)
    runner = service.runner
    assert isinstance(runner, FakeCrewRunner)
    assert runner.last_plan_day_inputs is not None
    assert runner.last_plan_day_inputs.get("include_breakfast") == "true"


def test_persist_planned_day_rolls_back_cursor_on_put_failure(
    dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = TripService(
        table=dynamodb_table,
        runner=FakeCrewRunner(),
        safety=NoopSafetyGate(),
    )
    trip_id = _ready_trip(service)

    def boom(**_kwargs: Any) -> Any:
        raise TypeError("Float types are not supported")

    monkeypatch.setattr(repo, "put_day_if_absent", boom)
    with pytest.raises(TypeError):
        service.plan_next_day(USER, trip_id)

    trip = repo.get_trip_meta(user_sub=USER, trip_id=trip_id, table=dynamodb_table)
    assert trip is not None
    assert int(trip["next_day_index"]) == 1
    leftover = [
        i
        for i in repo.get_trip_bundle(
            user_sub=USER, trip_id=trip_id, table=dynamodb_table
        )
        if i.get("entity_type") == "DAY"
    ]
    assert leftover == []
