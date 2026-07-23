import type { Route, Trip } from "../types/trip";

/** Trip still in progress (not finished planning all days). */
export function isTripIncomplete(trip: Pick<Trip, "status">): boolean {
  return trip.status !== "complete";
}

/**
 * Prefer the newest incomplete trip. `trips` should already be newest-first
 * (API sorts by created_at desc).
 */
export function pickLatestIncompleteTrip(trips: Trip[]): Trip | null {
  return trips.find(isTripIncomplete) ?? null;
}

/** Short label for lists: destination · date range. */
export function tripListLabel(trip: Pick<Trip, "destination" | "start_date" | "end_date">): string {
  return `${trip.destination} · ${trip.start_date} – ${trip.end_date}`;
}

export function tripStatusLabel(status: string): string {
  return status.replaceAll("_", " ");
}

/**
 * True when Days should kick off plan-next-day (empty itinerary, route ready).
 * Covers fresh confirm and reopening an old trip that never planned day 1.
 */
export function shouldAutoStartDayPlanning(bundle: {
  trip: Pick<Trip, "status" | "day_count" | "destination_type">;
  route: Pick<Route, "status"> | null | undefined;
  days: readonly unknown[];
}): boolean {
  if (bundle.days.length > 0) return false;
  if (bundle.trip.day_count < 1) return false;
  const status = bundle.trip.status;
  if (status === "complete") return false;
  if (
    status === "routing_confirmed" ||
    status === "planning" ||
    status === "failed"
  ) {
    return true;
  }
  if (bundle.trip.destination_type === "city") return true;
  return bundle.route?.status === "confirmed";
}
