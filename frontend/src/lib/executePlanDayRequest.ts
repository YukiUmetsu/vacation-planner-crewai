/** Pure plan-next-day request flow (sync 200 or async 202 + poll). */

import { getTrip, planNextDay } from "../api/trips";
import type { DayPlan, Trip } from "../types/trip";
import { pollUntilDayReady } from "./pollPlanDay";

export type PlanDayResult = { day: DayPlan; trip: Trip };

/** Must stay aligned with backend PLANNING_STALE_SECONDS (6 minutes). */
export const PLANNING_STALE_MS = 6 * 60 * 1000;

function dayReadyInBundle(
  trip: Trip,
  days: DayPlan[],
  planningDayIndex: number,
): PlanDayResult | null {
  const day = days.find((d) => d.day_index === planningDayIndex);
  if (!day) return null;
  const next = Number(trip.next_day_index ?? 1);
  if (!Number.isFinite(next) || next <= planningDayIndex) return null;
  return { day, trip };
}

function isStuckDay(
  trip: Trip,
  days: DayPlan[],
  planningDayIndex: number,
): boolean {
  const day = days.find((d) => d.day_index === planningDayIndex);
  if (!day) return false;
  const next = Number(trip.next_day_index ?? 1);
  return Number.isFinite(next) && next <= planningDayIndex;
}

export function isStalePlanningClaim(
  trip: Trip,
  nowMs: number = Date.now(),
): boolean {
  const started = trip.planning_started_at;
  if (!started || trip.planning_day_index == null) return false;
  const t = Date.parse(started);
  if (!Number.isFinite(t)) return false;
  return nowMs - t >= PLANNING_STALE_MS;
}

async function postFinalizeOrReclaim(
  id: string,
  resumeDayIndex: number,
): Promise<PlanDayResult | null> {
  try {
    const started = await planNextDay(id);
    if (started.status === 200 && started.day.day_index === resumeDayIndex) {
      return { day: started.day, trip: started.trip };
    }
    if (
      started.status === 202 &&
      started.planning_day_index === resumeDayIndex
    ) {
      return pollUntilDayReady(id, resumeDayIndex);
    }
  } catch {
    // Fall through — caller polls.
  }
  return null;
}

/**
 * Start or resume plan-next-day.
 *
 * Resume POST is allowed only for:
 * - stuck DAY (written, cursor not advanced), or
 * - stale claim (≥6 min) so BFF can reclaim after Event drop.
 * Fresh in-flight claims are poll-only (avoids GET→POST starting day N+1).
 */
export async function executePlanDayRequest(
  id: string,
  options?: {
    resumeDayIndex?: number;
    onAsyncStarted?: (trip: Trip) => void;
  },
): Promise<PlanDayResult> {
  const resumeDayIndex = options?.resumeDayIndex;
  if (resumeDayIndex != null) {
    const bundle = await getTrip(id);
    const already = dayReadyInBundle(bundle.trip, bundle.days, resumeDayIndex);
    if (already) {
      return already;
    }

    const needsFinalizePost =
      isStuckDay(bundle.trip, bundle.days, resumeDayIndex) ||
      (Number(bundle.trip.planning_day_index) === resumeDayIndex &&
        isStalePlanningClaim(bundle.trip));

    if (needsFinalizePost) {
      const again = await getTrip(id);
      const readyNow = dayReadyInBundle(again.trip, again.days, resumeDayIndex);
      if (readyNow) {
        return readyNow;
      }
      const stillNeedsPost =
        isStuckDay(again.trip, again.days, resumeDayIndex) ||
        (Number(again.trip.planning_day_index) === resumeDayIndex &&
          isStalePlanningClaim(again.trip));
      if (stillNeedsPost) {
        const finalized = await postFinalizeOrReclaim(id, resumeDayIndex);
        if (finalized) {
          return finalized;
        }
      }
    }

    const claim = bundle.trip.planning_day_index;
    if (claim != null && Number(claim) === resumeDayIndex) {
      options?.onAsyncStarted?.(bundle.trip);
    }
    return pollUntilDayReady(id, resumeDayIndex);
  }

  const started = await planNextDay(id);
  if (started.status === 200) {
    return { day: started.day, trip: started.trip };
  }
  options?.onAsyncStarted?.(started.trip);
  return pollUntilDayReady(id, started.planning_day_index);
}
