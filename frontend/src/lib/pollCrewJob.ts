/** Poll GET /trips/:id until an async crew job finishes. */

import { getTrip } from "../api/trips";
import type { CitySuggestion } from "../api/trips";
import type { DayPlan, Place, Route, Trip, TripBundle } from "../types/trip";
import {
  CREW_JOB_POLL,
  nextPollDelayMs,
  parseStartedAtMs,
  sleep,
  waitUntilVisible,
} from "./asyncPoll";

const DEFAULT_MAX_MS = 4 * 60 * 1000;

async function pollTrip(
  tripId: string,
  isDone: (bundle: TripBundle) => boolean,
  isFailed: (bundle: TripBundle) => boolean,
  failMessage: string,
  options?: {
    signal?: AbortSignal;
    maxMs?: number;
    startedAt?: string | null;
  },
): Promise<TripBundle> {
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

    const delay = nextPollDelayMs(CREW_JOB_POLL, {
      attempt,
      startedAtMs,
    });
    await sleep(delay, signal);
    attempt += 1;

    const bundle = await getTrip(tripId);
    startedAtMs =
      parseStartedAtMs(bundle.trip.crew_job_started_at) ?? startedAtMs;

    if (isDone(bundle)) {
      return bundle;
    }
    if (isFailed(bundle)) {
      throw new Error(bundle.trip.crew_job_error?.trim() || failMessage);
    }
  }

  throw new Error("Timed out waiting for the suggestion. Try refreshing.");
}

export async function pollUntilProposeReady(
  tripId: string,
  options?: {
    signal?: AbortSignal;
    maxMs?: number;
    startedAt?: string | null;
  },
): Promise<{ trip: Trip; route: Route | null }> {
  const bundle = await pollTrip(
    tripId,
    (b) =>
      b.trip.crew_job_kind == null &&
      !b.trip.crew_job_error &&
      b.route?.status === "proposed",
    (b) => b.trip.crew_job_kind == null && Boolean(b.trip.crew_job_error),
    "City proposal failed. Please try again.",
    options,
  );
  return { trip: bundle.trip, route: bundle.route };
}

export async function pollUntilSuggestCityReady(
  tripId: string,
  options?: {
    signal?: AbortSignal;
    maxMs?: number;
    startedAt?: string | null;
  },
): Promise<{ candidates: CitySuggestion[]; trip: Trip }> {
  const bundle = await pollTrip(
    tripId,
    (b) =>
      b.trip.crew_job_kind == null &&
      !b.trip.crew_job_error &&
      Array.isArray(b.trip.suggest_city_candidates) &&
      b.trip.suggest_city_candidates.length > 0,
    (b) => b.trip.crew_job_kind == null && Boolean(b.trip.crew_job_error),
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
  options?: {
    signal?: AbortSignal;
    maxMs?: number;
    startedAt?: string | null;
  },
): Promise<{ place: Place; day: DayPlan; trip: Trip }> {
  const bundle = await pollTrip(
    tripId,
    (b) => {
      if (b.trip.crew_job_kind != null) return false;
      if (b.trip.crew_job_error) return false;
      const day = b.days.find((d) => d.day_index === dayIndex);
      return Boolean(day && (day.places?.length ?? 0) > baselinePlaceCount);
    },
    (b) => b.trip.crew_job_kind == null && Boolean(b.trip.crew_job_error),
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
