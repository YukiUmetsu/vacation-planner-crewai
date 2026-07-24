/** Thin product analytics → POST /events (allowlisted names). */

import { apiFetch } from "../api/http";

const ALLOWED = new Set([
  "proposal_accepted",
  "proposal_accepted_without_edit",
  "plan_regenerated",
  "place_deleted",
  "place_reordered",
  "suggestion_accepted",
  "manual_edit",
  "time_to_accept",
]);

export type ProductEventName =
  | "proposal_accepted"
  | "proposal_accepted_without_edit"
  | "plan_regenerated"
  | "place_deleted"
  | "place_reordered"
  | "suggestion_accepted"
  | "manual_edit"
  | "time_to_accept";

export async function trackProductEvent(
  eventName: ProductEventName,
  opts: {
    tripId?: string;
    dayIndex?: number;
    payload?: Record<string, unknown>;
  } = {},
): Promise<void> {
  if (!ALLOWED.has(eventName)) return;
  try {
    await apiFetch("/events", {
      method: "POST",
      body: JSON.stringify({
        event_name: eventName,
        trip_id: opts.tripId ?? null,
        day_index: opts.dayIndex ?? null,
        payload: opts.payload ?? {},
        client_ts: new Date().toISOString(),
      }),
    });
  } catch {
    // Analytics must not break the UX.
  }
}
