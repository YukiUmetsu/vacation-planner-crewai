"""Unit tests for trip prompt helpers."""

from __future__ import annotations

from trips.prompts import (
    append_prior_day_summary_line,
    prior_day_summary_line,
    rebuild_prior_days_summary,
)


def test_rebuild_prior_days_summary_includes_place_names() -> None:
    days = [
        {
            "day_index": 1,
            "theme": "Old town walk",
            "overnight_city": "Shanghai",
            "places": [
                {"name": "Three Kingdoms Restaurant Shanghai", "place_key": "three-kingdoms-shanghai"},
                {"name": "Yu Garden", "place_key": "yu-garden"},
            ],
        },
        {
            "day_index": 2,
            "theme": "Capital museums",
            "overnight_city": "Beijing",
            "places": [],
        },
    ]
    summary = rebuild_prior_days_summary(days)
    assert "Day 1: Old town walk @ Shanghai — Three Kingdoms Restaurant Shanghai, Yu Garden" in summary
    assert "Day 2: Capital museums @ Beijing" in summary
    assert "—" not in summary.splitlines()[1]


def test_rebuild_prior_days_summary_caps_names_at_eight() -> None:
    places = [{"name": f"Place {i}", "place_key": f"p{i}"} for i in range(1, 12)]
    summary = rebuild_prior_days_summary(
        [{"day_index": 1, "theme": "Busy", "overnight_city": "Tokyo", "places": places}]
    )
    assert "Place 1" in summary
    assert "Place 8" in summary
    assert "Place 9" not in summary


def test_prior_day_summary_line_matches_plan_next_day_writer() -> None:
    line = prior_day_summary_line(
        day_index=1,
        theme="Old town walk",
        overnight_city="Shanghai",
        places=[
            {"name": "Three Kingdoms Restaurant Shanghai"},
            {"name": "Yu Garden"},
        ],
    )
    assert line == (
        "Day 1: Old town walk @ Shanghai — Three Kingdoms Restaurant Shanghai, Yu Garden"
    )
    summary = append_prior_day_summary_line("", line)
    summary = append_prior_day_summary_line(
        summary,
        prior_day_summary_line(
            day_index=2,
            theme="Capital museums",
            overnight_city="Beijing",
            places=[],
        ),
    )
    assert summary == (
        "Day 1: Old town walk @ Shanghai — Three Kingdoms Restaurant Shanghai, Yu Garden\n"
        "Day 2: Capital museums @ Beijing"
    )
