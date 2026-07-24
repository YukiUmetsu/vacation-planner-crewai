"""Unit tests for plan-next-day LLM retry input edits."""

from __future__ import annotations

from datetime import date

from services.plan_day_retry import (
    MAX_PLAN_DAY_ATTEMPTS,
    apply_plan_day_retry_inputs,
    labels_to_ban_after_failure,
    merge_banned_labels,
    place_labels,
    rejected_quality_labels,
    should_retry_plan_day,
)


MONDAY = date(2026, 9, 7)


def test_place_labels_unique() -> None:
    assert place_labels(
        [
            {"name": "Senso-ji"},
            {"name": "senso-ji"},
            {"name": "  "},
            {"name": "Tsukiji"},
        ]
    ) == ["Senso-ji", "Tsukiji"]


def test_apply_retry_inputs_attempt_zero_unchanged() -> None:
    base = {"preferences": "food", "overnight_city": "Tokyo", "target_place_count": "5"}
    out = apply_plan_day_retry_inputs(
        base, attempt=0, failure_code=None, banned_places=[]
    )
    assert out == base


def test_apply_retry_inputs_does_not_stack_hints() -> None:
    base = {
        "preferences": "food",
        "overnight_city": "Tokyo",
        "target_place_count": "5",
    }
    first = apply_plan_day_retry_inputs(
        base,
        attempt=1,
        failure_code="quality_empty",
        banned_places=["Closed Cafe"],
    )
    second = apply_plan_day_retry_inputs(
        base,
        attempt=2,
        failure_code="quality_empty",
        banned_places=["Closed Cafe", "Old Shop"],
    )
    assert first["preferences"].count("RETRY") == 1
    assert second["preferences"].startswith("FINAL RETRY")
    assert second["preferences"].count("FINAL RETRY") == 1
    assert " | RETRY (" not in second["preferences"]
    assert second["target_place_count"] == "7"


def test_apply_retry_inputs_bans_and_bumps_target() -> None:
    base = {
        "preferences": "food",
        "overnight_city": "Tokyo",
        "target_place_count": "5",
    }
    first = apply_plan_day_retry_inputs(
        base,
        attempt=1,
        failure_code="quality_empty",
        banned_places=["Closed Cafe"],
    )
    assert "RETRY (quality_empty)" in first["preferences"]
    assert "Closed Cafe" in first["preferences"]
    assert first["target_place_count"] == "5"


def test_composition_retry_does_not_ban_places() -> None:
    places = [
        {"name": "Lunch", "category": "food", "operational_status": "open"},
        {"name": "Dinner", "category": "food", "operational_status": "open"},
        {"name": "Park", "category": "park", "operational_status": "open"},
    ]
    assert (
        labels_to_ban_after_failure(
            code="missing_meals",
            places=places,
            plan_date=MONDAY,
        )
        == []
    )
    assert (
        labels_to_ban_after_failure(
            code="food_only_day",
            places=places,
            plan_date=MONDAY,
        )
        == []
    )
    hint = apply_plan_day_retry_inputs(
        {"preferences": "x", "overnight_city": "Tokyo"},
        attempt=1,
        failure_code="missing_meals",
        banned_places=[],
    )
    assert "meal/day-balance" in hint["preferences"]


def test_quality_empty_bans_only_rejected() -> None:
    places = [
        {"name": "Closed Cafe", "operational_status": "closed", "estimated_minutes": 60},
        {
            "name": "Open Park",
            "operational_status": "open",
            "estimated_minutes": 60,
        },
        {
            "name": "Visited Shrine",
            "operational_status": "open",
            "estimated_minutes": 60,
            "place_key": "visited-shrine|x",
        },
    ]
    banned = labels_to_ban_after_failure(
        code="quality_empty",
        places=places,
        plan_date=MONDAY,
        profile_visited_names={"visited shrine"},
    )
    assert "Closed Cafe" in banned
    assert "Visited Shrine" in banned
    assert "Open Park" not in banned


def test_rejected_quality_labels() -> None:
    assert rejected_quality_labels(
        [{"name": "X", "operational_status": "closed", "estimated_minutes": 30}],
        plan_date=MONDAY,
    ) == ["X"]


def test_should_retry_plan_day() -> None:
    assert should_retry_plan_day(code="quality_empty", attempt=0)
    assert should_retry_plan_day(code="dedupe_empty", attempt=1)
    assert not should_retry_plan_day(code="quality_empty", attempt=2)
    assert not should_retry_plan_day(code="energy_overload", attempt=0)
    assert MAX_PLAN_DAY_ATTEMPTS == 3


def test_merge_banned_labels() -> None:
    assert merge_banned_labels(["A"], ["a", "B"]) == ["A", "B"]
