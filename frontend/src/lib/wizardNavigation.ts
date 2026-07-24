import type { Route, Trip } from "../types/trip";

export type WizardStep = "details" | "cities" | "days";

export const WIZARD_STEPS: readonly WizardStep[] = [
  "details",
  "cities",
  "days",
] as const;

export type WizardNavContext = {
  demoMode: boolean;
  hasTrip: boolean;
  /** Confirmed city route, or city destination that skips propose. */
  routeReady: boolean;
  hasDays: boolean;
};

/** Whether the top step rail may navigate to ``next``. */
export function canNavigateToStep(
  next: WizardStep,
  ctx: WizardNavContext,
): boolean {
  if (ctx.demoMode) return true;
  if (next === "details") return true;
  if (next === "cities") return ctx.hasTrip;
  // Days: need a trip and either a ready route or existing day plans.
  return ctx.hasTrip && (ctx.routeReady || ctx.hasDays);
}

export function isRouteReadyForDays(input: {
  trip: Pick<Trip, "status" | "destination_type"> | null | undefined;
  route: Pick<Route, "status"> | null | undefined;
}): boolean {
  const trip = input.trip;
  if (!trip) return false;
  if (trip.destination_type === "city") return true;
  const status = trip.status;
  if (
    status === "routing_confirmed" ||
    status === "planning" ||
    status === "complete" ||
    status === "failed"
  ) {
    return true;
  }
  return input.route?.status === "confirmed";
}
