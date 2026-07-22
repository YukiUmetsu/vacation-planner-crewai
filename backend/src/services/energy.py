"""Traveler energy → warning thresholds (minutes). Keep in sync with docs/PLANNING_QUALITY.md."""

from __future__ import annotations

# Caution starts above this total (activity + travel). Overloaded above 1.2×.
MAX_COMFORTABLE_TOTAL_MINUTES: dict[int, int] = {
    1: 270,  # 4.5h
    2: 390,  # 6.5h
    3: 510,  # 8.5h
    4: 720,  # 12h
    5: 840,  # 14h
}


def clamp_energy_level(value: int | float | None) -> int:
    if value is None:
        return 3
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return 3
    if n <= 1:
        return 1
    if n >= 5:
        return 5
    return n


def max_minutes_for_energy(energy_level: int | float | None) -> int:
    level = clamp_energy_level(energy_level)
    return MAX_COMFORTABLE_TOTAL_MINUTES[level]
