from datetime import date

import pytest
from pydantic import ValidationError

from vacation_planner_models import (
    CityRoute,
    CityStop,
    DayPlan,
    DestinationType,
    Place,
    PlaceCategory,
    make_place_key,
    normalize_place_text,
)


def test_normalize_place_text_collapses_whitespace_and_case() -> None:
    assert normalize_place_text("  Senso-ji   Temple ") == "senso-ji temple"


def test_make_place_key() -> None:
    assert make_place_key("Senso-ji", "Asakusa, Tokyo") == "senso-ji|asakusa, tokyo"
    assert make_place_key("Senso-ji", None) == "senso-ji|"


def test_place_autofills_place_key() -> None:
    place = Place(name="Senso-ji", address="Asakusa")
    assert place.place_key == "senso-ji|asakusa"


def test_place_keeps_explicit_place_key() -> None:
    place = Place(name="Senso-ji", address="Asakusa", place_key="custom|key")
    assert place.place_key == "custom|key"


def _three_places() -> list[Place]:
    return [
        Place(
            name="Lunch Spot",
            address="1",
            category=PlaceCategory.food,
            reason_to_visit="Lunch — ramen",
        ),
        Place(name="Museum", address="2", category=PlaceCategory.museum),
        Place(
            name="Dinner Spot",
            address="3",
            category=PlaceCategory.food,
            reason_to_visit="Dinner — izakaya",
        ),
    ]


def test_day_plan_requires_three_to_seven_places() -> None:
    with pytest.raises(ValidationError):
        DayPlan(
            day_index=1,
            date=date(2026, 8, 1),
            overnight_city="Tokyo",
            places=_three_places()[:2],
        )

    # Seven places is the max; eight must fail schema validation.
    with pytest.raises(ValidationError):
        DayPlan(
            day_index=1,
            date=date(2026, 8, 1),
            overnight_city="Tokyo",
            places=_three_places() + [
                Place(name="D", address="4", category=PlaceCategory.park),
                Place(name="E", address="5", category=PlaceCategory.park),
                Place(name="F", address="6", category=PlaceCategory.park),
                Place(name="G", address="7", category=PlaceCategory.park),
                Place(name="H", address="8", category=PlaceCategory.park),
            ],
        )


def test_day_plan_assigns_order_when_unset() -> None:
    plan = DayPlan(
        day_index=1,
        date=date(2026, 8, 1),
        overnight_city="Tokyo",
        places=_three_places(),
    )
    assert [p.order_in_day for p in plan.places] == [1, 2, 3]


def test_day_plan_requires_two_food_meal_stops() -> None:
    with pytest.raises(ValidationError, match="lunch and dinner"):
        DayPlan(
            day_index=1,
            date=date(2026, 8, 1),
            overnight_city="Tokyo",
            places=[
                Place(name="A", address="1"),
                Place(name="B", address="2"),
                Place(name="C", address="3"),
            ],
        )


def test_day_plan_requires_overnight_city() -> None:
    with pytest.raises(ValidationError):
        DayPlan(
            day_index=1,
            date=date(2026, 8, 1),
            overnight_city="",
            places=_three_places(),
        )


def test_city_route_autofills_total_nights() -> None:
    route = CityRoute(
        destination_type=DestinationType.country,
        cities=[
            CityStop(city="Tokyo", nights=4, arrival_day_index=1, departure_day_index=4),
            CityStop(city="Kyoto", nights=3, arrival_day_index=5, departure_day_index=7),
        ],
    )
    assert route.total_nights == 7


def test_city_route_rejects_mismatched_total_nights() -> None:
    with pytest.raises(ValidationError):
        CityRoute(
            destination_type=DestinationType.country,
            cities=[
                CityStop(city="Tokyo", nights=4, arrival_day_index=1, departure_day_index=4),
            ],
            total_nights=99,
        )


def test_city_stop_rejects_inverted_day_window() -> None:
    with pytest.raises(ValidationError):
        CityStop(city="Tokyo", nights=2, arrival_day_index=5, departure_day_index=2)
