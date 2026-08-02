"""Traveler energy → warning thresholds (minutes). Keep in sync with docs/PLANNING_QUALITY.md."""

from __future__ import annotations

import math
from typing import Literal

# Soft comfort table (activity + travel). Auto-trim day plans at ≥ ENERGY_OVERLOAD_RATIO.
MAX_COMFORTABLE_TOTAL_MINUTES: dict[int, int] = {
    1: 270,  # 4.5h
    2: 390,  # 6.5h
    3: 510,  # 8.5h
    4: 720,  # 12h
    5: 840,  # 14h
}

# Soft warning above comfort. Generated day plans are trimmed when total ≥ 150%.
ENERGY_OVERLOAD_RATIO = 1.5

EnergyLoadBand = Literal["ok", "caution", "overloaded"]


def energy_load_ratio(total_minutes: int, comfort_max_minutes: int) -> float:
    if comfort_max_minutes <= 0:
        return 0.0
    return max(0, int(total_minutes)) / int(comfort_max_minutes)


def classify_energy_load(
    total_minutes: int, comfort_max_minutes: int
) -> EnergyLoadBand:
    """Map day load to ok / caution (soft) / overloaded (≥150%)."""
    ratio = energy_load_ratio(total_minutes, comfort_max_minutes)
    if ratio <= 1.0:
        return "ok"
    if ratio < ENERGY_OVERLOAD_RATIO:
        return "caution"
    return "overloaded"


def energy_overload_limit_minutes(comfort_max_minutes: int) -> int:
    """Minimum total minutes that counts as overloaded (ceil(comfort × 1.5))."""
    return math.ceil(int(comfort_max_minutes) * ENERGY_OVERLOAD_RATIO)


# Backward-compatible name for older callers/tests; energy no longer hard-fails.
ENERGY_HARD_OVERLOAD_RATIO = ENERGY_OVERLOAD_RATIO
hard_energy_limit_minutes = energy_overload_limit_minutes

# Soft compose target (meals count as places). Hard schema remains 3–7.
# Energy 3 ≈ lunch + ~3 activities + dinner → 5 stops.
TARGET_PLACE_COUNT_BY_ENERGY: dict[int, int] = {
    1: 3,
    2: 4,
    3: 5,
    4: 6,
    5: 7,
}

# Hard cap for DayPlan schema / BFF suggest-place (keep in sync with models).
MAX_PLACES_PER_DAY = 7
MIN_PLACES_PER_DAY = 3


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


def target_place_count_for_energy(energy_level: int | float | None) -> int:
    """Preferred stop count for day_plan compose (soft; not a hard BFF gate)."""
    level = clamp_energy_level(energy_level)
    return TARGET_PLACE_COUNT_BY_ENERGY[level]
