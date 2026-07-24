import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("../api/trips", () => ({
  getTrip: vi.fn(),
  proposeCities: vi.fn(),
  confirmCities: vi.fn(),
  suggestPlace: vi.fn(),
  removePlace: vi.fn(),
  deleteDay: vi.fn(),
}));

vi.mock("./productEvents", () => ({
  trackProductEvent: vi.fn().mockResolvedValue(undefined),
}));

import { confirmCities, getTrip } from "../api/trips";
import { trackProductEvent } from "./productEvents";
import {
  buildConfirmRoute,
  routeAcceptanceFingerprint,
  useLiveTripActions,
  type LiveTripState,
} from "./liveTrip";
import type { Route, TripBundle } from "../types/trip";

const getTripMock = vi.mocked(getTrip);
const confirmCitiesMock = vi.mocked(confirmCities);
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
    });
  });
});
