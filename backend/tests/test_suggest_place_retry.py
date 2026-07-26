"""Unit tests for suggest-place closed/weekday retry helpers."""

from __future__ import annotations

from datetime import date

from planning_quality.suggest_place_retry import (
    MAX_SUGGEST_PLACE_ATTEMPTS,
    apply_suggest_place_retry_inputs,
    merge_banned_labels,
    rejected_suggest_labels,
    should_retry_suggest_place,
)

MONDAY = date(2026, 9, 7)


def test_should_retry_weekday_closed_until_max() -> None:
    assert should_retry_suggest_place(code="place_weekday_closed", attempt=0)
    assert should_retry_suggest_place(code="place_closed", attempt=1)
    assert should_retry_suggest_place(code="place_duplicate", attempt=0)
    assert not should_retry_suggest_place(code="place_weekday_closed", attempt=2)
    assert not should_retry_suggest_place(code="day_full", attempt=0)
    assert MAX_SUGGEST_PLACE_ATTEMPTS == 3


def test_rejected_labels_and_merge() -> None:
    labels = rejected_suggest_labels(
        {
            "name": "Monday Museum",
            "place_key": "monday-museum",
            "place_id": "ChIJabc",
        }
    )
    assert "Monday Museum" in labels
    assert "monday-museum" in labels
    assert "ChIJabc" in labels
    merged = merge_banned_labels(labels, ["Monday Museum", "Other"])
    assert merged.count("Monday Museum") == 1
    assert "Other" in merged


def test_retry_inputs_ban_closed_and_mention_weekday() -> None:
    base = {
        "preferences": "parks",
        "already_visited": "senso-ji",
        "overnight_city": "Tokyo",
    }
    first = apply_suggest_place_retry_inputs(
        base,
        attempt=1,
        failure_code="place_weekday_closed",
        plan_date=MONDAY,
        banned_places=["Monday Museum", "monday-museum"],
    )
    prefs = str(first["preferences"])
    assert "RETRY (place_weekday_closed)" in prefs
    assert "weekday=0" in prefs
    assert "Monday Museum" in prefs
    assert "monday-museum" in str(first["already_visited"])
    assert "senso-ji" in str(first["already_visited"])

    final = apply_suggest_place_retry_inputs(
        base,
        attempt=2,
        failure_code="place_weekday_closed",
        plan_date=MONDAY,
        banned_places=["Monday Museum"],
    )
    assert "FINAL RETRY (place_weekday_closed)" in str(final["preferences"])


def test_retry_inputs_for_permanently_closed() -> None:
    base = {"preferences": "food", "already_visited": ""}
    out = apply_suggest_place_retry_inputs(
        base,
        attempt=1,
        failure_code="place_closed",
        plan_date=MONDAY,
        banned_places=["Shuttered Cafe"],
    )
    prefs = str(out["preferences"])
    assert "RETRY (place_closed)" in prefs
    assert "permanently closed" in prefs
    assert "weekday=" not in prefs
    assert "Shuttered Cafe" in str(out["already_visited"])
