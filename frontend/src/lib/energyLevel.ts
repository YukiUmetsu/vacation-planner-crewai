/** Traveler energy level: 1 = low / limited mobility, 5 = high capacity. */
export type EnergyLevel = 1 | 2 | 3 | 4 | 5;

export const ENERGY_LEVELS: readonly EnergyLevel[] = [1, 2, 3, 4, 5];

export const ENERGY_LEVEL_LABELS: Record<EnergyLevel, string> = {
  1: "Very low — limited mobility or needs long rests",
  2: "Low — short days, frequent breaks",
  3: "Moderate — balanced sightseeing",
  4: "High — long active days",
  5: "Very high — packed itineraries OK",
};

/** Soft warning threshold: total day minutes (activity + travel) by energy level.
 * Canonical table: docs/PLANNING_QUALITY.md — keep in sync.
 * Caution starts above this; overloaded above 1.2×.
 */
export const MAX_COMFORTABLE_TOTAL_MINUTES: Record<EnergyLevel, number> = {
  1: 270, // 4.5h
  2: 390, // 6.5h
  3: 510, // 8.5h
  4: 720, // 12h
  5: 840, // 14h
};

export type DayEnergyLoad = {
  level: EnergyLevel;
  totalMinutes: number;
  comfortMaxMinutes: number;
  overByMinutes: number;
  /** Ratio of total to comfort max (1 = at cap). */
  loadRatio: number;
  severity: "ok" | "caution" | "overloaded";
  message: string | null;
};

export function clampEnergyLevel(value: number): EnergyLevel {
  if (!Number.isFinite(value)) return 3;
  const n = Math.round(value);
  if (n <= 1) return 1;
  if (n >= 5) return 5;
  return n as EnergyLevel;
}

/**
 * Compare a day's total planned minutes to the traveler's energy comfort cap.
 */
export function assessDayEnergyLoad(
  energyLevel: EnergyLevel,
  totalMinutes: number,
): DayEnergyLoad {
  const level = clampEnergyLevel(energyLevel);
  const minutes = Number.isFinite(totalMinutes) ? Math.max(0, totalMinutes) : 0;
  const comfortMaxMinutes = MAX_COMFORTABLE_TOTAL_MINUTES[level];
  const overByMinutes = Math.max(0, minutes - comfortMaxMinutes);
  const loadRatio =
    comfortMaxMinutes > 0 ? minutes / comfortMaxMinutes : 0;

  let severity: DayEnergyLoad["severity"] = "ok";
  let message: string | null = null;

  if (minutes <= 0) {
    return {
      level,
      totalMinutes: minutes,
      comfortMaxMinutes,
      overByMinutes: 0,
      loadRatio: 0,
      severity: "ok",
      message: null,
    };
  }

  if (loadRatio > 1.2) {
    severity = "overloaded";
    message =
      level <= 2
        ? `This day looks too full for energy level ${level}. Consider fewer stops or shorter visits (${overByMinutes} min over a comfortable day).`
        : `This day exceeds a comfortable load for energy level ${level} by about ${overByMinutes} minutes.`;
  } else if (loadRatio > 1) {
    severity = "caution";
    message = `A bit packed for energy level ${level} — about ${overByMinutes} minutes over a comfortable day.`;
  }

  return {
    level,
    totalMinutes: minutes,
    comfortMaxMinutes,
    overByMinutes,
    loadRatio,
    severity,
    message,
  };
}
