import { apiFetch } from "./http";
import type { CreateTripInput, DayPlan, Place, Route, Trip, TripBundle } from "../types/trip";

export async function createTrip(input: CreateTripInput) {
  return apiFetch<{ trip: Trip; route: Route | null }>("/trips", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function listTrips(): Promise<{ trips: Trip[] }> {
  return apiFetch<{ trips: Trip[] }>("/trips", { method: "GET" });
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

/** Strip frontend-only fields before sending cities to the API. */
export function routeForConfirmRequest(route: Route): Record<string, unknown> {
  const cities = route.cities.map(({ client_id: _clientId, ...city }) => city);
  return {
    destination_type: route.destination_type,
    cities,
    rationale: route.rationale,
    total_nights: route.total_nights,
    status: "confirmed",
  };
}

export function confirmCities(tripId: string, route: Route) {
  return apiFetch<{ trip: Trip; route: Route | null }>(`/trips/${tripId}/cities`, {
    method: "PUT",
    body: JSON.stringify(routeForConfirmRequest(route)),
  });
}

export function planNextDay(tripId: string) {
  return apiFetch<{ day: DayPlan; trip: Trip }>(`/trips/${tripId}/plan-next-day`, {
    method: "POST",
    body: "{}",
  });
}

export function suggestPlace(tripId: string, dayIndex: number) {
  return apiFetch<{ place: Place; day: DayPlan; trip: Trip }>(
    `/trips/${tripId}/days/${dayIndex}/suggest-place`,
    { method: "POST", body: "{}" },
  );
}
