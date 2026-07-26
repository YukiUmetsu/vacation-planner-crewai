/** Poll GET /trips/:id until a planned day appears or planning fails. */

import { getTrip } from "../api/trips";
import { messageForApiError } from "../api/http";
import type { DayPlan, Trip } from "../types/trip";
import {
  PLAN_DAY_POLL,
  nextPollDelayMs,
  parseStartedAtMs,
  sleep,
  waitUntilVisible,
} from "./asyncPoll";

const DEFAULT_MAX_MS = 4 * 60 * 1000;

export type PollPlanResult = { day: DayPlan; trip: Trip };

function dayReady(
  trip: Trip,
  day: DayPlan | undefined,
  planningDayIndex: number,
): day is DayPlan {
  if (!day) return false;
  const next = Number(trip.next_day_index ?? 1);
  // Wait until cursor advanced so a stuck claim (DAY written, trip not updated) keeps polling.
  return Number.isFinite(next) && next > planningDayIndex;
}

/**
 * Poll trip bundle until DAY for planningDayIndex exists, or planning failed.
 * Waits through a quiet window first (GenAI rarely finishes in seconds), then
 * backs off toward expected completion — fewer Lambda GETs than a 1s loop.
 * Wall-clock timeout pauses while the tab is hidden.
 */
export async function pollUntilDayReady(
  tripId: string,
  planningDayIndex: number,
  options?: {
    signal?: AbortSignal;
    maxMs?: number;
    /** When known (202 response / hydrate), skip a full quiet wait on resume. */
    startedAt?: string | null;
  },
): Promise<PollPlanResult> {
  const maxMs = options?.maxMs ?? DEFAULT_MAX_MS;
  const signal = options?.signal;
  let deadline = Date.now() + maxMs;
  let attempt = 0;
  let startedAtMs = parseStartedAtMs(options?.startedAt);

  while (Date.now() < deadline) {
    if (typeof document !== "undefined" && document.visibilityState === "hidden") {
      const hiddenAt = Date.now();
      await waitUntilVisible(signal);
      deadline += Date.now() - hiddenAt;
    }

    const delay = nextPollDelayMs(PLAN_DAY_POLL, {
      attempt,
      startedAtMs,
    });
    await sleep(delay, signal);
    attempt += 1;

    const bundle = await getTrip(tripId);
    startedAtMs =
      parseStartedAtMs(bundle.trip.planning_started_at) ?? startedAtMs;

    const day = bundle.days.find((d) => d.day_index === planningDayIndex);
    if (dayReady(bundle.trip, day, planningDayIndex)) {
      return { day, trip: bundle.trip };
    }

    const stillPlanning = bundle.trip.planning_day_index === planningDayIndex;
    const failed =
      !stillPlanning &&
      (bundle.trip.status === "failed" || Boolean(bundle.trip.planning_error));

    if (failed) {
      const detail = String(bundle.trip.planning_error || "").trim();
      throw new Error(
        messageForApiError(422, undefined, detail) ||
          "Day planning failed. Please try again.",
      );
    }
  }

  throw new Error("Timed out waiting for the day plan. Try refreshing.");
}
