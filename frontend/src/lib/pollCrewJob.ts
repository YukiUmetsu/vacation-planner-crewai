/** Poll GET /trips/:id until an async crew job finishes. */

import { getTrip } from "../api/trips";
import type { CitySuggestion } from "../api/trips";
import type { DayPlan, Place, Route, Trip, TripBundle } from "../types/trip";

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

async function pollTrip(
  tripId: string,
  isDone: (bundle: TripBundle) => boolean,
  isFailed: (bundle: TripBundle) => boolean,
  failMessage: string,
  options?: { signal?: AbortSignal; maxMs?: number },
): Promise<TripBundle> {
  const maxMs = options?.maxMs ?? DEFAULT_MAX_MS;
  const signal = options?.signal;
  let deadline = Date.now() + maxMs;
  let delay = INITIAL_DELAY_MS;

  while (Date.now() < deadline) {
    if (typeof document !== "undefined" && document.visibilityState === "hidden") {
      const hiddenAt = Date.now();
      await waitUntilVisible(signal);
      deadline += Date.now() - hiddenAt;
    }

    const bundle = await getTrip(tripId);
    if (isDone(bundle)) {
      return bundle;
    }
    if (isFailed(bundle)) {
      throw new Error(
        bundle.trip.crew_job_error?.trim() || failMessage,
      );
    }

    await sleep(delay, signal);
    delay = Math.min(MAX_DELAY_MS, Math.round(delay * 1.5));
  }

  throw new Error("Timed out waiting for the suggestion. Try refreshing.");
}

export async function pollUntilProposeReady(
  tripId: string,
  options?: { signal?: AbortSignal; maxMs?: number },
): Promise<{ trip: Trip; route: Route | null }> {
  const bundle = await pollTrip(
    tripId,
    (b) =>
      b.trip.crew_job_kind == null &&
      !b.trip.crew_job_error &&
      b.route?.status === "proposed",
    (b) =>
      b.trip.crew_job_kind == null && Boolean(b.trip.crew_job_error),
    "City proposal failed. Please try again.",
    options,
  );
  return { trip: bundle.trip, route: bundle.route };
}

export async function pollUntilSuggestCityReady(
  tripId: string,
  options?: { signal?: AbortSignal; maxMs?: number },
): Promise<{ candidates: CitySuggestion[]; trip: Trip }> {
  const bundle = await pollTrip(
    tripId,
    (b) =>
      b.trip.crew_job_kind == null &&
      !b.trip.crew_job_error &&
      Array.isArray(b.trip.suggest_city_candidates) &&
      b.trip.suggest_city_candidates.length > 0,
    (b) =>
      b.trip.crew_job_kind == null && Boolean(b.trip.crew_job_error),
    "City suggestion failed. Please try again.",
    options,
  );
  return {
    candidates: bundle.trip.suggest_city_candidates ?? [],
    trip: bundle.trip,
  };
}

export async function pollUntilSuggestPlaceReady(
  tripId: string,
  dayIndex: number,
  baselinePlaceCount: number,
  options?: { signal?: AbortSignal; maxMs?: number },
): Promise<{ place: Place; day: DayPlan; trip: Trip }> {
  const bundle = await pollTrip(
    tripId,
    (b) => {
      if (b.trip.crew_job_kind != null) return false;
      if (b.trip.crew_job_error) return false;
      const day = b.days.find((d) => d.day_index === dayIndex);
      return Boolean(day && (day.places?.length ?? 0) > baselinePlaceCount);
    },
    (b) =>
      b.trip.crew_job_kind == null && Boolean(b.trip.crew_job_error),
    "Place suggestion failed. Please try again.",
    options,
  );
  const day = bundle.days.find((d) => d.day_index === dayIndex);
  if (!day || !day.places?.length) {
    throw new Error("Place suggestion failed. Please try again.");
  }
  const place = day.places[day.places.length - 1];
  return { place, day, trip: bundle.trip };
}
