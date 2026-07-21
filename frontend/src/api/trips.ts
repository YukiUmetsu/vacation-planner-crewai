import { apiFetch } from "./http";
import type { CreateTripInput, DayPlan, Route, Trip, TripBundle} from "../types/trip";

export async function createTrip(input: CreateTripInput) {
    return apiFetch<{trip: Trip; route: Route | null}>("/trips", {
        method: "POST",
        body: JSON.stringify(input),
    });
}

export async function getTrip(tripId: string): Promise<TripBundle> {
    return apiFetch<TripBundle>(`/trips/${tripId}`);
}

export function proposeCities(tripId: string) {
    return apiFetch<{ trip: Trip; route: Route | null }>(
      `/trips/${tripId}/propose-cities`,
      { method: "POST", body: "{}" },
    );
  }
  export function confirmCities(tripId: string, route: Route) {
    return apiFetch<{ trip: Trip; route: Route | null }>(
      `/trips/${tripId}/cities`,
      {
        method: "PUT",
        body: JSON.stringify({ ...route, status: "confirmed" }),
      },
    );
  }
  export function planNextDay(tripId: string) {
    return apiFetch<{ day: DayPlan; trip: Trip }>(
      `/trips/${tripId}/plan-next-day`,
      { method: "POST", body: "{}" },
    );
  }