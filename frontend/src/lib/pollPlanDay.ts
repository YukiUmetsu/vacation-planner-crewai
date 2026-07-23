/** Poll GET /trips/:id until a planned day appears or planning fails. */

import { getTrip } from "../api/trips";
import type { DayPlan, Trip } from "../types/trip";

const DEFAULT_MAX_MS = 4 * 60 * 1000;
const INITIAL_DELAY_MS = 1000;
const MAX_DELAY_MS = 5000;

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

function waitUntilVisible(signal?: AbortSignal): Promise<void> {
  if (typeof document === "undefined" || document.visibilityState === "visible") {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const onVis = () => {
      if (document.visibilityState === "visible") {
        cleanup();
        resolve();
      }
    };
    const onAbort = () => {
      cleanup();
      reject(new DOMException("Aborted", "AbortError"));
    };
    const cleanup = () => {
      document.removeEventListener("visibilitychange", onVis);
      signal?.removeEventListener("abort", onAbort);
    };
    document.addEventListener("visibilitychange", onVis);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

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
 * Wall-clock timeout pauses while the tab is hidden so backgrounding does not
 * false-timeout a completed job.
 */
export async function pollUntilDayReady(
  tripId: string,
  planningDayIndex: number,
  options?: { signal?: AbortSignal; maxMs?: number },
): Promise<PollPlanResult> {
  const maxMs = options?.maxMs ?? DEFAULT_MAX_MS;
  const signal = options?.signal;
  let deadline = Date.now() + maxMs;
  let delay = INITIAL_DELAY_MS;

  while (Date.now() < deadline) {
    if (typeof document !== "undefined" && document.visibilityState === "hidden") {
      const hiddenAt = Date.now();
      await waitUntilVisible(signal);
      // Do not charge hidden time against the timeout.
      deadline += Date.now() - hiddenAt;
      // Fall through to an immediate fetch now that we are visible again.
    }

    const bundle = await getTrip(tripId);
    const day = bundle.days.find((d) => d.day_index === planningDayIndex);
    if (dayReady(bundle.trip, day, planningDayIndex)) {
      return { day, trip: bundle.trip };
    }

    const stillPlanning = bundle.trip.planning_day_index === planningDayIndex;
    const failed =
      !stillPlanning &&
      (bundle.trip.status === "failed" || Boolean(bundle.trip.planning_error));

    if (failed) {
      throw new Error("Day planning failed. Please try again.");
    }

    await sleep(delay, signal);
    delay = Math.min(MAX_DELAY_MS, Math.round(delay * 1.5));
  }

  throw new Error("Timed out waiting for the day plan. Try refreshing.");
}
