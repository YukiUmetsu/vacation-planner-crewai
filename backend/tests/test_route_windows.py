"""Tests for CityRoute day-window normalization and pacing."""

from __future__ import annotations

import pytest

from http_utils import ApiError
from services.route_windows import (
    _largest_remainder_partition,
    _scale_nights,
    consolidate_route_cities,
    max_cities_for_trip,
    normalize_route_windows,
)
from services.trip_service import _assert_route_fits_window


@pytest.mark.parametrize(
    ("day_count", "expected"),
    [
        (1, 1),  # 0 nights
        (2, 1),  # 1 night
        (4, 1),  # 3 nights
        (5, 2),  # 4 nights
        (6, 3),  # 5 nights
        (7, 3),  # 6 nights — not 5 one-night hops
        (9, 3),  # 8 nights
        (10, 4),  # 9 nights
        (14, 4),  # 13 nights
        (15, 5),  # 14 nights
        (30, 5),
    ],
)
def test_max_cities_for_trip_thresholds(day_count: int, expected: int) -> None:
    assert max_cities_for_trip(day_count=day_count) == expected


# --- _largest_remainder_partition -------------------------------------------------


def test_largest_remainder_empty_weights() -> None:
    assert _largest_remainder_partition(10, []) == []


def test_largest_remainder_single_slot_takes_all() -> None:
    assert _largest_remainder_partition(7, [5]) == [7]
    assert _largest_remainder_partition(1, [99]) == [1]


def test_largest_remainder_docstring_example() -> None:
    # 7 trip days, night-weights [3, 5] → contiguous spans [3, 4]
    assert _largest_remainder_partition(7, [3, 5]) == [3, 4]


def test_largest_remainder_equal_weights_split_evenly() -> None:
    assert _largest_remainder_partition(9, [1, 1, 1]) == [3, 3, 3]
    assert _largest_remainder_partition(8, [2, 2, 2]) == [3, 3, 2]


def test_largest_remainder_total_equals_slot_count() -> None:
    assert _largest_remainder_partition(3, [9, 1, 1]) == [1, 1, 1]


def test_largest_remainder_zero_and_negative_weights_treated_as_one() -> None:
    # max(1, w) so zeros/negatives still get a positive share (weights → [1, 1, 3]).
    assert _largest_remainder_partition(5, [0, -2, 3]) == [1, 1, 3]


@pytest.mark.parametrize(
    ("total", "weights"),
    [
        (7, [3, 5]),
        (10, [1, 1, 1, 1]),
        (11, [4, 1, 1]),
        (15, [1, 2, 3, 4]),
        (6, [100, 1]),
        (20, [1, 1, 1, 1, 1]),
    ],
)
def test_largest_remainder_invariants(total: int, weights: list[int]) -> None:
    parts = _largest_remainder_partition(total, weights)
    assert len(parts) == len(weights)
    assert sum(parts) == total
    assert all(p >= 1 for p in parts)


def test_largest_remainder_rejects_more_slots_than_days() -> None:
    with pytest.raises(ApiError) as err:
        _largest_remainder_partition(2, [1, 1, 1])
    assert err.value.status_code == 400
    assert err.value.code == "route_too_many_cities"


def test_largest_remainder_heavier_weight_gets_more_or_equal() -> None:
    parts = _largest_remainder_partition(10, [1, 9])
    assert parts[1] > parts[0]
    parts2 = _largest_remainder_partition(10, [9, 1])
    assert parts2[0] > parts2[1]


# --- _scale_nights ----------------------------------------------------------------


def test_scale_nights_empty() -> None:
    assert _scale_nights([], 5) == []


def test_scale_nights_already_matching() -> None:
    assert _scale_nights([2, 4], 6) == [2, 4]


def test_scale_nights_zero_raw_distributes_evenly() -> None:
    assert _scale_nights([0, 0, 0], 5) == [2, 2, 1]
    assert _scale_nights([0, 0], 0) == [0, 0]


def test_scale_nights_scales_down_proportionally() -> None:
    scaled = _scale_nights([10, 10], 4)
    assert sum(scaled) == 4
    assert scaled == [2, 2]


def test_scale_nights_scales_up_proportionally() -> None:
    scaled = _scale_nights([1, 3], 8)
    assert sum(scaled) == 8
    assert scaled[1] > scaled[0]


def test_scale_nights_negative_expected_clamped() -> None:
    assert _scale_nights([1, 1], -3) == [0, 0]


# --- consolidate / normalize ------------------------------------------------------


def test_normalize_fixes_overlapping_transfer_day() -> None:
    """Crew often double-counts the transfer day (e.g. both claim day 3)."""
    raw = {
        "destination_type": "country",
        "cities": [
            {
                "city": "Tokyo",
                "country": "Japan",
                "nights": 2,
                "arrival_day_index": 1,
                "departure_day_index": 3,
                "reason": "capital",
                "highlights": [],
            },
            {
                "city": "Kyoto",
                "country": "Japan",
                "nights": 4,
                "arrival_day_index": 3,
                "departure_day_index": 7,
                "reason": "temples",
                "highlights": [],
            },
        ],
        "rationale": "overlap on day 3",
        "total_nights": 6,
        "status": "proposed",
    }
    with pytest.raises(ApiError) as before:
        _assert_route_fits_window(raw, 7)
    assert before.value.code == "route_overlap"

    fixed = normalize_route_windows(raw, 7)
    _assert_route_fits_window(fixed, 7)
    assert fixed["cities"][0]["departure_day_index"] + 1 == fixed["cities"][1][
        "arrival_day_index"
    ]
    assert fixed["cities"][0]["arrival_day_index"] == 1
    assert fixed["cities"][-1]["departure_day_index"] == 7
    assert fixed["total_nights"] == 6
    assert sum(int(c["nights"]) for c in fixed["cities"]) == 6


def test_normalize_consolidates_too_many_cities_for_short_trip() -> None:
    raw = {
        "destination_type": "country",
        "cities": [
            {"city": "Tokyo", "nights": 1, "arrival_day_index": 1, "departure_day_index": 1},
            {"city": "Yokohama", "nights": 1, "arrival_day_index": 2, "departure_day_index": 2},
            {"city": "Nagoya", "nights": 1, "arrival_day_index": 3, "departure_day_index": 3},
            {"city": "Kyoto", "nights": 1, "arrival_day_index": 4, "departure_day_index": 4},
            {"city": "Osaka", "nights": 2, "arrival_day_index": 5, "departure_day_index": 7},
        ],
        "total_nights": 6,
        "status": "proposed",
    }
    assert len(consolidate_route_cities(raw, day_count=7)["cities"]) == 3
    fixed = normalize_route_windows(raw, 7)
    assert len(fixed["cities"]) <= 3
    _assert_route_fits_window(fixed, 7)
    names = [c["city"] for c in fixed["cities"]]
    assert "Osaka" in names


def test_consolidate_merges_lightest_into_previous_and_notes_absorbed() -> None:
    raw = {
        "cities": [
            {"city": "Tokyo", "nights": 3, "reason": "base", "highlights": ["A"]},
            {"city": "Hakone", "nights": 1, "reason": "onsen", "highlights": ["B"]},
            {"city": "Kyoto", "nights": 3, "reason": "temples", "highlights": ["C"]},
            {"city": "Osaka", "nights": 2, "reason": "food", "highlights": ["D"]},
        ],
    }
    # 7 days → 6 nights → max 3 cities; lightest mid-stop (Hakone) merges into Tokyo.
    out = consolidate_route_cities(raw, day_count=7)
    assert len(out["cities"]) == 3
    assert out["cities"][0]["city"] == "Tokyo"
    assert out["cities"][0]["nights"] == 4
    assert "Also covers Hakone" in out["cities"][0]["reason"]
    assert "A" in out["cities"][0]["highlights"]
    assert "B" in out["cities"][0]["highlights"]


def test_normalize_scales_nights_to_day_count() -> None:
    raw = {
        "destination_type": "country",
        "cities": [
            {
                "city": "A",
                "nights": 10,
                "arrival_day_index": 1,
                "departure_day_index": 2,
            },
            {
                "city": "B",
                "nights": 10,
                "arrival_day_index": 2,
                "departure_day_index": 5,
            },
        ],
        "total_nights": 20,
        "status": "proposed",
    }
    fixed = normalize_route_windows(raw, 5)
    _assert_route_fits_window(fixed, 5)
    assert fixed["total_nights"] == 4
    assert len(fixed["cities"]) <= 2


def test_normalize_windows_cover_every_day_exactly_once() -> None:
    raw = {
        "cities": [
            {"city": "A", "nights": 1},
            {"city": "B", "nights": 1},
            {"city": "C", "nights": 1},
        ],
    }
    fixed = normalize_route_windows(raw, 7)
    _assert_route_fits_window(fixed, 7)
    spans = [
        c["departure_day_index"] - c["arrival_day_index"] + 1 for c in fixed["cities"]
    ]
    assert sum(spans) == 7
    assert all(s >= 1 for s in spans)
