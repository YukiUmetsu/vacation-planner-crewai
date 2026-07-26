import { isCognitoConfigured } from "../auth/config";
import { logout } from "../auth/oauth";
import { apiFetch, ApiError, getApiBaseUrl, buildAuthHeaders, messageForApiError } from "./http";
import type { CreateTripInput, DayPlan, Place, Route, Trip, TripBundle } from "../types/trip";

export async function createTrip(input: CreateTripInput) {
  return apiFetch<{ trip: Trip; route: Route | null }>("/trips", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateTrip(tripId: string, input: CreateTripInput) {
  return apiFetch<{ trip: Trip; route: Route | null }>(`/trips/${tripId}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export async function listTrips(): Promise<{ trips: Trip[] }> {
  return apiFetch<{ trips: Trip[] }>("/trips", { method: "GET" });
}

export async function getTrip(tripId: string): Promise<TripBundle> {
  return apiFetch<TripBundle>(`/trips/${tripId}`);
}

export async function deleteTrip(
  tripId: string,
): Promise<{
  ok: boolean;
  trip_id: string;
  deleted: { TRIP: number; ROUTE: number; DAY: number; total: number };
}> {
  return apiFetch(`/trips/${tripId}`, { method: "DELETE" });
}

export async function proposeCities(tripId: string): Promise<
  | { status: 200; trip: Trip; route: Route | null }
  | { status: 202; trip: Trip; job: string }
> {
  const headers = await buildAuthHeaders();
  const res = await fetch(`${getApiBaseUrl()}/trips/${tripId}/propose-cities`, {
    method: "POST",
    headers,
    body: "{}",
  });
  const data = (await res.json().catch(() => ({}))) as {
    error?: string;
    message?: string;
    code?: string;
    trip?: Trip;
    route?: Route | null;
    job?: string;
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
    if (!data.trip || !data.job) {
      throw new ApiError(502, "async propose-cities missing trip payload");
    }
    return { status: 202, trip: data.trip, job: data.job };
  }
  if (!data.trip) {
    throw new ApiError(502, "propose-cities missing trip payload");
  }
  return { status: 200, trip: data.trip, route: data.route ?? null };
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
  return apiFetch<{ trip: Trip; route: Route | null; days: DayPlan[] }>(
    `/trips/${tripId}/cities`,
    {
      method: "PUT",
      body: JSON.stringify(routeForConfirmRequest(route)),
    },
  );
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
        : messageForApiError(
            res.status,
            data.code,
            data.error ?? data.message ?? res.statusText,
          );
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

export async function suggestPlace(
  tripId: string,
  dayIndex: number,
  body?: { hint?: string },
): Promise<
  | { status: 200; place: Place; day: DayPlan; trip: Trip }
  | {
      status: 202;
      trip: Trip;
      job: string;
      day_index: number;
      baseline_place_count: number;
    }
> {
  const headers = await buildAuthHeaders();
  const res = await fetch(
    `${getApiBaseUrl()}/trips/${tripId}/days/${dayIndex}/suggest-place`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(body ?? {}),
    },
  );
  const data = (await res.json().catch(() => ({}))) as {
    error?: string;
    message?: string;
    code?: string;
    place?: Place;
    day?: DayPlan;
    trip?: Trip;
    job?: string;
    day_index?: number;
    baseline_place_count?: number;
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
    if (
      !data.trip ||
      !data.job ||
      data.day_index == null ||
      data.baseline_place_count == null
    ) {
      throw new ApiError(502, "async suggest-place missing trip payload");
    }
    return {
      status: 202,
      trip: data.trip,
      job: data.job,
      day_index: data.day_index,
      baseline_place_count: data.baseline_place_count,
    };
  }
  if (!data.place || !data.day || !data.trip) {
    throw new ApiError(502, "suggest-place missing place payload");
  }
  return {
    status: 200,
    place: data.place,
    day: data.day,
    trip: data.trip,
  };
}

export function removePlace(
  tripId: string,
  dayIndex: number,
  placeIndex: number,
) {
  return apiFetch<{ day: DayPlan; trip: Trip }>(
    `/trips/${tripId}/days/${dayIndex}/places/${placeIndex}`,
    { method: "DELETE" },
  );
}

export function reorderPlace(
  tripId: string,
  dayIndex: number,
  fromIndex: number,
  toIndex: number,
) {
  return apiFetch<{ day: DayPlan; trip: Trip }>(
    `/trips/${tripId}/days/${dayIndex}/places/reorder`,
    {
      method: "POST",
      body: JSON.stringify({ from_index: fromIndex, to_index: toIndex }),
    },
  );
}

export type CitySuggestion = {
  city: string;
  country?: string;
  reason?: string;
  highlights?: string[];
  recommended_nights: number;
};

export async function suggestCity(
  tripId: string,
  body?: {
    cities?: Array<Record<string, unknown> | { city: string }>;
    hint?: string;
    count?: number;
  },
): Promise<
  | { status: 200; candidates: CitySuggestion[]; trip?: Trip }
  | { status: 202; trip: Trip; job: string }
> {
  const headers = await buildAuthHeaders();
  const res = await fetch(`${getApiBaseUrl()}/trips/${tripId}/suggest-city`, {
    method: "POST",
    headers,
    body: JSON.stringify(body ?? {}),
  });
  const data = (await res.json().catch(() => ({}))) as {
    error?: string;
    message?: string;
    code?: string;
    candidates?: CitySuggestion[];
    trip?: Trip;
    job?: string;
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
    if (!data.trip || !data.job) {
      throw new ApiError(502, "async suggest-city missing trip payload");
    }
    return { status: 202, trip: data.trip, job: data.job };
  }
  return {
    status: 200,
    candidates: data.candidates ?? [],
    trip: data.trip,
  };
}

export function deleteDay(tripId: string, dayIndex: number) {
  return apiFetch<{
    deleted_day_index: number;
    trip: Trip;
    days: DayPlan[];
  }>(`/trips/${tripId}/days/${dayIndex}`, { method: "DELETE" });
}
