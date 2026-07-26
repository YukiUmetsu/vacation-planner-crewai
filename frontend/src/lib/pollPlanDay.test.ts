import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { pollUntilDayReady } from "./pollPlanDay";
import { PLAN_DAY_POLL } from "./asyncPoll";
import type { TripBundle } from "../types/trip";

vi.mock("../api/trips", () => ({
  getTrip: vi.fn(),
}));

import { getTrip } from "../api/trips";

const getTripMock = vi.mocked(getTrip);

function bundle(
  partial: Partial<TripBundle["trip"]> & { days?: TripBundle["days"] },
): TripBundle {
  return {
    trip: {
      trip_id: "t1",
      origin: "NYC",
      destination: "Japan",
      destination_type: "country",
      start_date: "2026-08-01",
      end_date: "2026-08-07",
      day_count: 7,
      status: "planning",
      next_day_index: 1,
      ...partial,
    },
    route: null,
    days: partial.days ?? [],
  };
}

describe("pollUntilDayReady", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    getTripMock.mockReset();
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "visible",
    });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("resolves when the planned day appears and cursor advances", async () => {
    getTripMock
      .mockResolvedValueOnce(bundle({ planning_day_index: 1, days: [] }))
      .mockResolvedValueOnce(
        bundle({
          planning_day_index: null,
          next_day_index: 2,
          days: [
            {
              day_index: 1,
              date: "2026-08-01",
              theme: "Day 1",
              overnight_city: "Tokyo",
              places: [],
            },
          ],
        }),
      );

    const pending = pollUntilDayReady("t1", 1, { maxMs: 60_000 });
    // Quiet window, then first GET (still planning), then minDelay, then ready.
    await vi.advanceTimersByTimeAsync(PLAN_DAY_POLL.quietBeforeFirstMs);
    await vi.advanceTimersByTimeAsync(PLAN_DAY_POLL.minDelayMs);
    const result = await pending;
    expect(result.day.day_index).toBe(1);
    expect(getTripMock).toHaveBeenCalledTimes(2);
  });

  it("keeps polling when day exists but cursor not advanced", async () => {
    getTripMock
      .mockResolvedValueOnce(
        bundle({
          planning_day_index: 1,
          next_day_index: 1,
          days: [
            {
              day_index: 1,
              date: "2026-08-01",
              theme: "Day 1",
              overnight_city: "Tokyo",
              places: [],
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        bundle({
          planning_day_index: null,
          next_day_index: 2,
          days: [
            {
              day_index: 1,
              date: "2026-08-01",
              theme: "Day 1",
              overnight_city: "Tokyo",
              places: [],
            },
          ],
        }),
      );

    const pending = pollUntilDayReady("t1", 1, { maxMs: 60_000 });
    await vi.advanceTimersByTimeAsync(PLAN_DAY_POLL.quietBeforeFirstMs);
    await vi.advanceTimersByTimeAsync(PLAN_DAY_POLL.minDelayMs);
    const result = await pending;
    expect(result.trip.next_day_index).toBe(2);
    expect(getTripMock).toHaveBeenCalledTimes(2);
  });

  it("rejects when planning failed", async () => {
    getTripMock.mockResolvedValue(
      bundle({
        planning_day_index: null,
        status: "failed",
        planning_error: "crew_failed",
        days: [],
      }),
    );

    const pending = pollUntilDayReady("t1", 1, { maxMs: 60_000 });
    const expectation = expect(pending).rejects.toThrow(/crew_failed/);
    await vi.advanceTimersByTimeAsync(PLAN_DAY_POLL.quietBeforeFirstMs);
    await expectation;
  });

  it("rewrites legacy quality_empty planning_error copy", async () => {
    getTripMock.mockResolvedValue(
      bundle({
        planning_day_index: null,
        status: "failed",
        planning_error:
          "fewer than 3 open places remain after closed/visited filters; retry plan-next-day",
        days: [],
      }),
    );

    const pending = pollUntilDayReady("t1", 1, { maxMs: 60_000 });
    const expectation = expect(pending).rejects.toThrow(/Not enough open places/);
    await vi.advanceTimersByTimeAsync(PLAN_DAY_POLL.quietBeforeFirstMs);
    await expectation;
  });

  it("pauses timeout while the tab is hidden and fetches on visible", async () => {
    let visibility: DocumentVisibilityState = "hidden";
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => visibility,
    });

    getTripMock.mockResolvedValue(
      bundle({
        planning_day_index: null,
        next_day_index: 2,
        days: [
          {
            day_index: 1,
            date: "2026-08-01",
            theme: "Day 1",
            overnight_city: "Tokyo",
            places: [],
          },
        ],
      }),
    );

    const pending = pollUntilDayReady("t1", 1, { maxMs: 60_000 });
    // Wall clock advances while hidden — must not timeout or GET.
    await vi.advanceTimersByTimeAsync(20_000);
    expect(getTripMock).not.toHaveBeenCalled();

    visibility = "visible";
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(PLAN_DAY_POLL.quietBeforeFirstMs);
    const result = await pending;
    expect(result.day.day_index).toBe(1);
    expect(getTripMock).toHaveBeenCalledTimes(1);
  });
});
