"""Tests for energy → minute and place-count targets."""

from __future__ import annotations

from services.energy import (
    max_minutes_for_energy,
    target_place_count_for_energy,
)


def test_target_place_count_by_energy() -> None:
    assert target_place_count_for_energy(1) == 3
    assert target_place_count_for_energy(2) == 4
    assert target_place_count_for_energy(3) == 5
    assert target_place_count_for_energy(4) == 6
    assert target_place_count_for_energy(5) == 7
    assert target_place_count_for_energy(None) == 5


def test_max_minutes_energy_3() -> None:
    assert max_minutes_for_energy(3) == 510
