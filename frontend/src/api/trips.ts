import { isCognitoConfigured } from "../auth/config";
import { logout } from "../auth/oauth";
import { apiFetch, ApiError, getApiBaseUrl, buildAuthHeaders } from "./http";
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

export type PlanNextDaySyncResult = {
  status: 200;
  day: DayPlan;
  trip: Trip;
};

export type PlanNextDayAsyncResult = {
  status: 202;
  trip: Trip;
  planning_day_index: number;
};

export type PlanNextDayResult = PlanNextDaySyncResult | PlanNextDayAsyncResult;

export async function planNextDay(tripId: string): Promise<PlanNextDayResult> {
  const headers = await buildAuthHeaders();
  const res = await fetch(`${getApiBaseUrl()}/trips/${tripId}/plan-next-day`, {
    method: "POST",
    headers,
    body: "{}",
  });
  const data = (await res.json().catch(() => ({}))) as {
    error?: string;
    message?: string;
    code?: string;
    day?: DayPlan;
    trip?: Trip;
    planning_day_index?: number;
  };
  if (!res.ok) {
    if (res.status === 401) {
      if (isCognitoConfigured()) {
        logout();
      }
      throw new ApiError(
        401,
        "Session expired or missing — sign in again.",
        "unauthorized",
      );
    }
    const detail =
      res.status >= 500
        ? "Something went wrong. Please try again."
        : (data.error ?? data.message ?? res.statusText);
    throw new ApiError(res.status, detail, data.code);
  }
  if (res.status === 202) {
    if (!data.trip || data.planning_day_index == null) {
      throw new ApiError(502, "async plan-next-day missing trip payload");
    }
    return {
      status: 202,
      trip: data.trip,
      planning_day_index: data.planning_day_index,
    };
  }
  if (!data.day || !data.trip) {
    throw new ApiError(502, "plan-next-day missing day payload");
  }
  return { status: 200, day: data.day, trip: data.trip };
}

export function suggestPlace(tripId: string, dayIndex: number) {
  return apiFetch<{ place: Place; day: DayPlan; trip: Trip }>(
    `/trips/${tripId}/days/${dayIndex}/suggest-place`,
    { method: "POST", body: "{}" },
  );
}
