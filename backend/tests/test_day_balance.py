"""Tests for day composition balance (food crawl + non-food requirement)."""

from __future__ import annotations

import pytest

from http_utils import ApiError
from services.day_balance import (
    day_balance_guidance,
    detect_food_crawl_mode,
    min_non_food_places_for,
    non_food_count,
    prefer_non_food_suggestion,
    require_day_balance,
    require_suggested_place_balance,
)


def test_detect_food_crawl_mode_phrases() -> None:
    assert detect_food_crawl_mode("We want a food crawl in Tokyo")
    assert detect_food_crawl_mode("restaurant tour please")
    assert detect_food_crawl_mode("", ["bar crawl"])
    assert detect_food_crawl_mode("tasting day in Osaka")
    assert not detect_food_crawl_mode("food, sushi, ramen, culture")
    assert not detect_food_crawl_mode("love ramen and temples")
    assert not detect_food_crawl_mode("")


def test_require_day_balance_rejects_food_only() -> None:
    places = [
        {"name": "Jiro", "category": "food"},
        {"name": "Narisawa", "category": "food"},
        {"name": "Tsuta", "category": "food"},
    ]
    with pytest.raises(ApiError) as exc:
        require_day_balance(places, food_crawl_mode=False)
    assert exc.value.code == "food_only_day"

    require_day_balance(places, food_crawl_mode=True)


def test_require_day_balance_accepts_mixed() -> None:
    places = [
        {"name": "Lunch", "category": "food"},
        {"name": "Senso-ji", "category": "other"},
        {"name": "Dinner", "category": "food"},
    ]
    require_day_balance(places, food_crawl_mode=False)
    assert non_food_count(places) == 1
    assert min_non_food_places_for(food_crawl_mode=False) == 1


def test_prefer_and_require_suggested_place_balance() -> None:
    existing = [
        {"name": "A", "category": "food"},
        {"name": "B", "category": "food"},
        {"name": "C", "category": "food"},
        {"name": "D", "category": "food"},
    ]
    assert prefer_non_food_suggestion(existing, food_crawl_mode=False)
    with pytest.raises(ApiError) as exc:
        require_suggested_place_balance(
            {"name": "E", "category": "food"},
            existing,
            food_crawl_mode=False,
        )
    assert exc.value.code == "food_only_day"

    require_suggested_place_balance(
        {"name": "Park", "category": "park"},
        existing,
        food_crawl_mode=False,
    )
    require_suggested_place_balance(
        {"name": "E", "category": "food"},
        existing,
        food_crawl_mode=True,
    )


def test_prefer_non_food_allows_meal_on_one_food_partial_day() -> None:
    """After deletes leave a single food stop, dinner must still be allowed."""
    one_food = [{"name": "Lunch", "category": "food"}]
    assert not prefer_non_food_suggestion(one_food, food_crawl_mode=False)
    require_suggested_place_balance(
        {"name": "Dinner", "category": "food"},
        one_food,
        food_crawl_mode=False,
    )

    two_food = [
        {"name": "Lunch", "category": "food"},
        {"name": "Cafe", "category": "food"},
    ]
    assert prefer_non_food_suggestion(two_food, food_crawl_mode=False)
    with pytest.raises(ApiError) as exc:
        require_suggested_place_balance(
            {"name": "Dinner", "category": "food"},
            two_food,
            food_crawl_mode=False,
        )
    assert exc.value.code == "food_only_day"


def test_day_balance_guidance_mentions_mode() -> None:
    text = day_balance_guidance(food_crawl_mode=False, min_non_food_places=1)
    assert "food_crawl_mode=false" in text
    assert "non-food" in text.lower()
    crawl = day_balance_guidance(food_crawl_mode=True, min_non_food_places=0)
    assert "food_crawl_mode=true" in crawl


def test_day_shape_hint_scales_with_target() -> None:
    from services.day_balance import day_shape_hint

    assert "activity" in day_shape_hint(
        food_crawl_mode=False, target_place_count=5
    )
    assert day_shape_hint(food_crawl_mode=True, target_place_count=5) == "food_crawl"
