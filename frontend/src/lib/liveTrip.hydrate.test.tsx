import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("../api/trips", () => ({
  getTrip: vi.fn(),
  proposeCities: vi.fn(),
  confirmCities: vi.fn(),
  suggestPlace: vi.fn(),
  suggestCity: vi.fn(),
  removePlace: vi.fn(),
  reorderPlace: vi.fn(),
  deleteDay: vi.fn(),
}));

vi.mock("./productEvents", () => ({
  trackProductEvent: vi.fn().mockResolvedValue(undefined),
}));

import { confirmCities, getTrip, reorderPlace, suggestCity } from "../api/trips";
import { trackProductEvent } from "./productEvents";
import {
  buildConfirmRoute,
  routeAcceptanceFingerprint,
  useLiveTripActions,
  type LiveTripState,
} from "./liveTrip";
import type { DayPlan, Place, Route, TripBundle } from "../types/trip";

const getTripMock = vi.mocked(getTrip);
const confirmCitiesMock = vi.mocked(confirmCities);
const reorderPlaceMock = vi.mocked(reorderPlace);
const suggestCityMock = vi.mocked(suggestCity);
const trackProductEventMock = vi.mocked(trackProductEvent);

function bundleFor(id: string): TripBundle {
  return {
    trip: {
      trip_id: id,
      origin: "NYC",
      destination: "Japan",
      destination_type: "country",
      start_date: "2026-08-01",
      end_date: "2026-08-07",
      day_count: 7,
      status: "drafting",
    },
    route: null,
    days: [],
  };
}

function proposedBundle(id: string): TripBundle {
  const route: Route = {
    destination_type: "country",
    cities: [
      {
        city: "Tokyo",
        nights: 3,
        arrival_day_index: 1,
        departure_day_index: 3,
      },
    ],
    total_nights: 3,
    rationale: "Food first",
    status: "proposed",
    updated_at: "2026-07-20T12:00:00.000Z",
  };
  return {
    trip: {
      trip_id: id,
      origin: "NYC",
      destination: "Japan",
      destination_type: "country",
      start_date: "2026-08-01",
      end_date: "2026-08-07",
      day_count: 7,
      status: "awaiting_city_confirm",
    },
    route,
    days: [],
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useLiveTripActions hydrateFromApi", () => {
  beforeEach(() => {
    getTripMock.mockReset();
    confirmCitiesMock.mockReset();
    reorderPlaceMock.mockReset();
    suggestCityMock.mockReset();
    trackProductEventMock.mockReset();
    trackProductEventMock.mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
  });

  it("ignores a stale getTrip response after a newer hydrate starts", async () => {
    let resolveA: (value: TripBundle) => void = () => {};
    let resolveB: (value: TripBundle) => void = () => {};
    const pendingA = new Promise<TripBundle>((resolve) => {
      resolveA = resolve;
    });
    const pendingB = new Promise<TripBundle>((resolve) => {
      resolveB = resolve;
    });

    getTripMock.mockImplementation(async (id: string) => {
      if (id === "trip-a") return pendingA;
      if (id === "trip-b") return pendingB;
      throw new Error(`unexpected trip ${id}`);
    });

    let live: LiveTripState = {
      trip: null,
      cities: [],
      days: [],
      routeMeta: null,
    };
    const onApplied = vi.fn((updater) => {
      live = typeof updater === "function" ? updater(live) : updater;
    });

    const { result } = renderHook(
      () =>
        useLiveTripActions({
          tripId: null,
          onApplied,
          onActionError: vi.fn(),
        }),
      { wrapper },
    );

    let resultA: { applied: boolean; bundle: TripBundle } | undefined;
    let resultB: { applied: boolean; bundle: TripBundle } | undefined;

    await act(async () => {
      const pA = result.current.hydrateFromApi("trip-a").then((r) => {
        resultA = r;
      });
      const pB = result.current.hydrateFromApi("trip-b").then((r) => {
        resultB = r;
      });
      resolveB(bundleFor("trip-b"));
      resolveA(bundleFor("trip-a"));
      await Promise.all([pA, pB]);
    });

    await waitFor(() => {
      expect(resultA?.applied).toBe(false);
      expect(resultB?.applied).toBe(true);
    });
    expect(live.trip?.trip_id).toBe("trip-b");
    expect(onApplied).toHaveBeenCalledTimes(1);
  });

  it("ignores hydration after cancelPropose", async () => {
    let resolveTrip: (value: TripBundle) => void = () => {};
    getTripMock.mockImplementation(
      () =>
        new Promise<TripBundle>((resolve) => {
          resolveTrip = resolve;
        }),
    );

    let live: LiveTripState = {
      trip: null,
      cities: [],
      days: [],
      routeMeta: null,
    };
    const onApplied = vi.fn((updater) => {
      live = typeof updater === "function" ? updater(live) : updater;
    });

    const { result } = renderHook(
      () =>
        useLiveTripActions({
          tripId: "trip-a",
          onApplied,
          onActionError: vi.fn(),
        }),
      { wrapper },
    );

    let hydrateResult: { applied: boolean } | undefined;
    await act(async () => {
      const pending = result.current.hydrateFromApi("trip-a").then((r) => {
        hydrateResult = r;
      });
      result.current.cancelPropose();
      resolveTrip(bundleFor("trip-a"));
      await pending;
    });

    expect(hydrateResult?.applied).toBe(false);
    expect(live.trip).toBeNull();
    expect(onApplied).not.toHaveBeenCalled();
  });

  it("treats hydrated proposed route as acceptance baseline without edit", async () => {
    const bundle = proposedBundle("trip-resume");
    getTripMock.mockResolvedValue(bundle);
    confirmCitiesMock.mockImplementation(async (_id, route) => ({
      trip: { ...bundle.trip!, status: "planning" },
      route: { ...route, status: "confirmed" },
      days: [],
    }));

    let live: LiveTripState = {
      trip: null,
      cities: [],
      days: [],
      routeMeta: null,
    };
    const onApplied = vi.fn((updater) => {
      live = typeof updater === "function" ? updater(live) : updater;
    });

    const { result } = renderHook(
      () =>
        useLiveTripActions({
          tripId: "trip-resume",
          onApplied,
          onActionError: vi.fn(),
        }),
      { wrapper },
    );

    await act(async () => {
      await result.current.hydrateFromApi("trip-resume");
    });
    expect(live.cities).toHaveLength(1);

    const confirmRoute = buildConfirmRoute(live, live.cities);
    expect(routeAcceptanceFingerprint(confirmRoute)).toBe(
      routeAcceptanceFingerprint(bundle.route!),
    );

    await act(async () => {
      await result.current.confirmMutation.mutateAsync({
        id: "trip-resume",
        route: confirmRoute,
      });
    });

    await waitFor(() => {
      expect(trackProductEventMock).toHaveBeenCalledWith("proposal_accepted", {
        tripId: "trip-resume",
        payload: { source: "confirm_cities" },
      });
      expect(trackProductEventMock).toHaveBeenCalledWith(
        "proposal_accepted_without_edit",
        {
          tripId: "trip-resume",
          payload: { source: "confirm_cities" },
        },
      );
      expect(trackProductEventMock).toHaveBeenCalledWith(
        "time_to_accept",
        expect.objectContaining({
          tripId: "trip-resume",
          payload: expect.objectContaining({
            source: "confirm_cities",
            ms: expect.any(Number),
          }),
        }),
      );
    });
    const tta = trackProductEventMock.mock.calls.find(
      (call) => call[0] === "time_to_accept",
    );
    const ms = (tta?.[1] as { payload: { ms: number } }).payload.ms;
    // Hydrate uses route.updated_at (2026-07-20), not page-load "now".
    expect(ms).toBeGreaterThan(24 * 60 * 60 * 1000);
  });

  it("rolls back optimistic place order when reorderPlace rejects", async () => {
    const place = (name: string, order: number): Place => ({
      name,
      address: `${name} St`,
      category: "other",
      reason_to_visit: name,
      details: "",
      estimated_minutes: 30,
      order_in_day: order,
      place_key: name.toLowerCase(),
    });
    const previousDays: DayPlan[] = [
      {
        day_index: 1,
        date: "2026-09-01",
        overnight_city: "Tokyo",
        theme: "Start",
        places: [place("Alpha", 1), place("Beta", 2)],
      },
    ];
    let live: LiveTripState = {
      trip: {
        trip_id: "trip-reorder",
        origin: "NYC",
        destination: "Japan",
        destination_type: "country",
        start_date: "2026-09-01",
        end_date: "2026-09-07",
        day_count: 7,
        status: "planning",
      },
      cities: [],
      days: previousDays,
      routeMeta: null,
    };
    const onActionError = vi.fn();
    const onApplied = vi.fn((updater) => {
      live = typeof updater === "function" ? updater(live) : updater;
    });
    reorderPlaceMock.mockRejectedValue(new Error("reorder failed"));

    const { result } = renderHook(
      () =>
        useLiveTripActions({
          tripId: "trip-reorder",
          onApplied,
          onActionError,
        }),
      { wrapper },
    );

    // Simulate optimistic UI move, then API failure with snapshot rollback.
    live = {
      ...live,
      days: [
        {
          ...previousDays[0]!,
          places: [place("Beta", 1), place("Alpha", 2)],
        },
      ],
    };

    await act(async () => {
      result.current.runReorderPlace(1, 0, 1, previousDays);
    });

    await waitFor(() => {
      expect(onActionError).toHaveBeenCalledWith("reorder failed");
      expect(live.days[0]!.places.map((p) => p.name)).toEqual(["Alpha", "Beta"]);
    });
  });

  it("surfaces suggest_city candidates when hydrate resumes an in-flight job", async () => {
    const inFlight = proposedBundle("trip-suggest-resume");
    inFlight.trip = {
      ...inFlight.trip!,
      crew_job_kind: "suggest_city",
      crew_job_started_at: "2026-07-26T00:00:00.000Z",
    };
    const done: TripBundle = {
      ...inFlight,
      trip: {
        ...inFlight.trip!,
        crew_job_kind: null,
        crew_job_started_at: null,
        suggest_city_candidates: [
          {
            city: "Kanazawa",
            reason: "Garden city",
            recommended_nights: 2,
            highlights: ["Kenrokuen"],
          },
        ],
      },
    };

    let calls = 0;
    getTripMock.mockImplementation(async () => {
      calls += 1;
      return calls === 1 ? inFlight : done;
    });

    let live: LiveTripState = {
      trip: null,
      cities: [],
      days: [],
      routeMeta: null,
    };
    const onApplied = vi.fn((updater) => {
      live = typeof updater === "function" ? updater(live) : updater;
    });
    const onActionError = vi.fn();

    const { result } = renderHook(
      () =>
        useLiveTripActions({
          tripId: "trip-suggest-resume",
          onApplied,
          onActionError,
        }),
      { wrapper },
    );

    await act(async () => {
      await result.current.hydrateFromApi("trip-suggest-resume");
    });

    await waitFor(() => {
      expect(live.trip?.suggest_city_candidates?.map((c) => c.city)).toEqual([
        "Kanazawa",
      ]);
      expect(live.trip?.crew_job_kind ?? null).toBeNull();
    });
    expect(onActionError).not.toHaveBeenCalled();
  });

  it("surfaces suggestCity API errors to the caller", async () => {
    suggestCityMock.mockRejectedValue(new Error("No city suggestion returned."));
    const onActionError = vi.fn();
    const { result } = renderHook(
      () =>
        useLiveTripActions({
          tripId: "trip-suggest",
          onApplied: vi.fn(),
          onActionError,
        }),
      { wrapper },
    );

    await expect(
      act(async () => {
        await result.current.runSuggestCity({
          cities: [{ city: "Tokyo", nights: 3, arrival_day_index: 1, departure_day_index: 3 }],
          hint: "coastal",
        });
      }),
    ).rejects.toThrow(/No city suggestion/);

    expect(onActionError).toHaveBeenCalledWith("No city suggestion returned.");
  });

  it("returns suggestCity candidates without mutating local cities", async () => {
    suggestCityMock.mockResolvedValue({
      status: 200,
      candidates: [
        {
          city: "Osaka",
          reason: "Food",
          recommended_nights: 1,
          highlights: ["Dotonbori"],
        },
      ],
      trip: {
        trip_id: "trip-suggest",
        origin: "NYC",
        destination: "Japan",
        destination_type: "country",
        start_date: "2026-08-01",
        end_date: "2026-08-07",
        day_count: 7,
        status: "awaiting_city_confirm",
        crew_job_kind: null,
      },
    });
    let live: LiveTripState = {
      trip: null,
      cities: [
        {
          city: "Tokyo",
          nights: 3,
          arrival_day_index: 1,
          departure_day_index: 3,
        },
      ],
      days: [],
      routeMeta: null,
    };
    const onApplied = vi.fn((updater) => {
      live = typeof updater === "function" ? updater(live) : updater;
    });

    const { result } = renderHook(
      () =>
        useLiveTripActions({
          tripId: "trip-suggest",
          onApplied,
          onActionError: vi.fn(),
        }),
      { wrapper },
    );

    let candidates: Awaited<ReturnType<typeof result.current.runSuggestCity>> = [];
    await act(async () => {
      candidates = await result.current.runSuggestCity({
        cities: live.cities,
        count: 1,
      });
    });

    expect(candidates.map((c) => c.city)).toEqual(["Osaka"]);
    expect(live.cities.map((c) => c.city)).toEqual(["Tokyo"]);
    expect(onApplied).toHaveBeenCalled();
    expect(live.trip?.suggest_city_candidates?.map((c) => c.city)).toEqual([
      "Osaka",
    ]);
  });
});
