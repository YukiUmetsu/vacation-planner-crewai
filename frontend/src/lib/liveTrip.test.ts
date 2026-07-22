import { describe, expect, it } from "vitest";
import {
  applyTripBundle,
  buildConfirmRoute,
  emptyLiveTripState,
  pendingPlanningDayIndex,
} from "./liveTrip";
import type { TripBundle } from "../types/trip";

const sampleBundle: TripBundle = {
  trip: {
    trip_id: "t1",
    origin: "NYC",
    destination: "Japan",
    destination_type: "country",
    start_date: "2026-08-01",
    end_date: "2026-08-07",
    day_count: 7,
    status: "awaiting_city_confirm",
  },
  route: {
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
  },
  days: [],
};

describe("applyTripBundle", () => {
  it("copies cities and days from the bundle", () => {
    const state = applyTripBundle(sampleBundle);
    expect(state.trip?.trip_id).toBe("t1");
    expect(state.cities).toEqual(sampleBundle.route!.cities);
    expect(state.routeMeta?.rationale).toBe("Food first");
    expect(state.days).toEqual([]);
  });
});

describe("buildConfirmRoute", () => {
  it("builds a confirmed route from live state + edited cities", () => {
    const live = applyTripBundle(sampleBundle);
    const cities = [
      ...live.cities,
      {
        city: "Kyoto",
        nights: 2,
        arrival_day_index: 4,
        departure_day_index: 5,
      },
    ];
    const route = buildConfirmRoute(live, cities);
    expect(route.status).toBe("confirmed");
    expect(route.total_nights).toBe(5);
    expect(route.cities).toHaveLength(2);
    expect(route.rationale).toBe("Food first");
  });

  it("falls back when route meta is missing", () => {
    const live = emptyLiveTripState();
    live.trip = sampleBundle.trip;
    const route = buildConfirmRoute(live, []);
    expect(route.destination_type).toBe("country");
    expect(route.total_nights).toBe(0);
  });
});

describe("pendingPlanningDayIndex", () => {
  it("returns planning_day_index while claim is held", () => {
    const trip = {
      ...sampleBundle.trip,
      planning_day_index: 1,
      next_day_index: 1,
      status: "planning" as const,
    };
    expect(pendingPlanningDayIndex(trip, [])).toBe(1);
    expect(
      pendingPlanningDayIndex(trip, [
        {
          day_index: 1,
          date: "2026-08-01",
          theme: "Day 1",
          overnight_city: "Tokyo",
          places: [],
        },
      ]),
    ).toBe(1);
  });

  it("returns null when no claim", () => {
    expect(pendingPlanningDayIndex(sampleBundle.trip, [])).toBeNull();
  });
});
