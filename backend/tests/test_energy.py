"""Unit tests for traveler energy soft/overloaded bands and targets."""

from __future__ import annotations

from shared.energy import (
    ENERGY_OVERLOAD_RATIO,
    classify_energy_load,
    energy_overload_limit_minutes,
    max_minutes_for_energy,
    target_place_count_for_energy,
)


def test_overload_ratio_is_150_percent() -> None:
    assert ENERGY_OVERLOAD_RATIO == 1.5


def test_classify_soft_below_overload_at_and_above() -> None:
    comfort = 270
    assert classify_energy_load(270, comfort) == "ok"
    assert classify_energy_load(271, comfort) == "caution"
    assert classify_energy_load(404, comfort) == "caution"
    assert classify_energy_load(405, comfort) == "overloaded"
    assert classify_energy_load(500, comfort) == "overloaded"


def test_energy_overload_limit_uses_ceil() -> None:
    assert energy_overload_limit_minutes(270) == 405
    # Non-integer 1.5× must round up so limit matches ratio >= 1.5.
    assert energy_overload_limit_minutes(271) == 407
    assert classify_energy_load(406, 271) == "caution"
    assert classify_energy_load(407, 271) == "overloaded"


def test_target_place_count_by_energy() -> None:
    assert target_place_count_for_energy(1) == 3
    assert target_place_count_for_energy(2) == 4
    assert target_place_count_for_energy(3) == 5
    assert target_place_count_for_energy(4) == 6
    assert target_place_count_for_energy(5) == 7
    assert target_place_count_for_energy(None) == 5


def test_max_minutes_energy_3() -> None:
    assert max_minutes_for_energy(3) == 510
