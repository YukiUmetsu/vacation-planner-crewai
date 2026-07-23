import { describe, expect, it } from "vitest";
import {
  isTripIncomplete,
  pickLatestIncompleteTrip,
  shouldAutoStartDayPlanning,
  tripListLabel,
} from "./tripStatus";
import type { Trip } from "../types/trip";

function trip(partial: Partial<Trip> & Pick<Trip, "trip_id" | "status">): Trip {
  return {
    origin: "NYC",
    destination: "Japan",
    destination_type: "country",
    start_date: "2026-08-01",
    end_date: "2026-08-07",
    day_count: 7,
    ...partial,
  };
}

describe("isTripIncomplete", () => {
  it("treats complete as finished", () => {
    expect(isTripIncomplete(trip({ trip_id: "a", status: "complete" }))).toBe(
      false,
    );
  });

  it("treats drafting / planning / failed as incomplete", () => {
    expect(isTripIncomplete(trip({ trip_id: "a", status: "drafting" }))).toBe(
      true,
    );
    expect(isTripIncomplete(trip({ trip_id: "a", status: "planning" }))).toBe(
      true,
    );
    expect(isTripIncomplete(trip({ trip_id: "a", status: "failed" }))).toBe(
      true,
    );
  });
});

describe("pickLatestIncompleteTrip", () => {
  it("returns the first incomplete in a newest-first list", () => {
    const trips = [
      trip({ trip_id: "new-complete", status: "complete", destination: "Paris" }),
      trip({ trip_id: "open", status: "planning", destination: "Japan" }),
      trip({ trip_id: "old", status: "drafting", destination: "Italy" }),
    ];
    expect(pickLatestIncompleteTrip(trips)?.trip_id).toBe("open");
  });

  it("returns null when every trip is complete", () => {
    const trips = [
      trip({ trip_id: "a", status: "complete" }),
      trip({ trip_id: "b", status: "complete" }),
    ];
    expect(pickLatestIncompleteTrip(trips)).toBeNull();
  });
});

describe("tripListLabel", () => {
  it("formats destination and dates", () => {
    expect(
      tripListLabel({
        destination: "Japan",
        start_date: "2026-08-01",
        end_date: "2026-08-07",
      }),
    ).toBe("Japan · 2026-08-01 – 2026-08-07");
  });
});

describe("shouldAutoStartDayPlanning", () => {
  it("starts when routing is confirmed and days are empty", () => {
    expect(
      shouldAutoStartDayPlanning({
        trip: trip({ trip_id: "t", status: "routing_confirmed" }),
        route: { status: "confirmed" },
        days: [],
      }),
    ).toBe(true);
  });

  it("does not start when days already exist", () => {
    expect(
      shouldAutoStartDayPlanning({
        trip: trip({ trip_id: "t", status: "planning" }),
        route: { status: "confirmed" },
        days: [{ day_index: 1 }],
      }),
    ).toBe(false);
  });

  it("does not start while still awaiting city confirm", () => {
    expect(
      shouldAutoStartDayPlanning({
        trip: trip({ trip_id: "t", status: "awaiting_city_confirm" }),
        route: { status: "proposed" },
        days: [],
      }),
    ).toBe(false);
  });
});
