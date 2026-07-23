import { beforeEach, describe, expect, it, vi } from "vitest";
import { executePlanDayRequest } from "./executePlanDayRequest";
import type { DayPlan, Trip } from "../types/trip";

vi.mock("../api/trips", () => ({
  planNextDay: vi.fn(),
  getTrip: vi.fn(),
}));

vi.mock("./pollPlanDay", () => ({
  pollUntilDayReady: vi.fn(),
}));

import { getTrip, planNextDay } from "../api/trips";
import { pollUntilDayReady } from "./pollPlanDay";

const planNextDayMock = vi.mocked(planNextDay);
const getTripMock = vi.mocked(getTrip);
const pollMock = vi.mocked(pollUntilDayReady);

const trip = (partial: Partial<Trip> = {}): Trip => ({
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
});

const day: DayPlan = {
  day_index: 1,
  date: "2026-08-01",
  theme: "Day 1",
  overnight_city: "Tokyo",
  places: [],
};

describe("executePlanDayRequest", () => {
  beforeEach(() => {
    planNextDayMock.mockReset();
    getTripMock.mockReset();
    pollMock.mockReset();
  });

  it("returns sync 200 without polling", async () => {
    planNextDayMock.mockResolvedValue({
      status: 200,
      day,
      trip: trip({ next_day_index: 2 }),
    });
    const result = await executePlanDayRequest("t1");
    expect(result.day.day_index).toBe(1);
    expect(pollMock).not.toHaveBeenCalled();
    expect(getTripMock).not.toHaveBeenCalled();
  });

  it("polls after 202 and notifies onAsyncStarted", async () => {
    const asyncTrip = trip({ planning_day_index: 1 });
    planNextDayMock.mockResolvedValue({
      status: 202,
      trip: asyncTrip,
      planning_day_index: 1,
    });
    pollMock.mockResolvedValue({
      day,
      trip: trip({ next_day_index: 2, planning_day_index: null }),
    });
    const onAsyncStarted = vi.fn();
    const result = await executePlanDayRequest("t1", { onAsyncStarted });
    expect(onAsyncStarted).toHaveBeenCalledWith(asyncTrip);
    expect(pollMock).toHaveBeenCalledWith("t1", 1);
    expect(result.day.day_index).toBe(1);
  });

  it("on resume returns immediately when day already ready", async () => {
    getTripMock.mockResolvedValue({
      trip: trip({ next_day_index: 2, planning_day_index: null }),
      route: null,
      days: [day],
    });
    const result = await executePlanDayRequest("t1", { resumeDayIndex: 1 });
    expect(result.trip.next_day_index).toBe(2);
    expect(planNextDayMock).not.toHaveBeenCalled();
    expect(pollMock).not.toHaveBeenCalled();
  });

  it("on resume with in-flight claim polls without POST", async () => {
    const inFlight = trip({ planning_day_index: 1, next_day_index: 1 });
    getTripMock.mockResolvedValue({
      trip: inFlight,
      route: null,
      days: [],
    });
    pollMock.mockResolvedValue({
      day,
      trip: trip({ next_day_index: 2 }),
    });
    const onAsyncStarted = vi.fn();
    await executePlanDayRequest("t1", {
      resumeDayIndex: 1,
      onAsyncStarted,
    });
    expect(planNextDayMock).not.toHaveBeenCalled();
    expect(onAsyncStarted).toHaveBeenCalledWith(inFlight);
    expect(pollMock).toHaveBeenCalledWith("t1", 1);
  });

  it("on resume with cleared claim does not POST", async () => {
    getTripMock.mockResolvedValue({
      trip: trip({ next_day_index: 1, planning_day_index: null }),
      route: null,
      days: [],
    });
    pollMock.mockResolvedValue({
      day,
      trip: trip({ next_day_index: 2 }),
    });
    await executePlanDayRequest("t1", { resumeDayIndex: 1 });
    expect(planNextDayMock).not.toHaveBeenCalled();
    expect(pollMock).toHaveBeenCalledWith("t1", 1);
  });

  it("on resume with stuck DAY POSTs to finalize", async () => {
    getTripMock
      .mockResolvedValueOnce({
        trip: trip({ planning_day_index: 1, next_day_index: 1 }),
        route: null,
        days: [day],
      })
      .mockResolvedValueOnce({
        trip: trip({ planning_day_index: 1, next_day_index: 1 }),
        route: null,
        days: [day],
      });
    planNextDayMock.mockResolvedValue({
      status: 200,
      day,
      trip: trip({ next_day_index: 2, planning_day_index: null }),
    });
    const result = await executePlanDayRequest("t1", { resumeDayIndex: 1 });
    expect(getTripMock).toHaveBeenCalledTimes(2);
    expect(planNextDayMock).toHaveBeenCalledWith("t1");
    expect(result.trip.next_day_index).toBe(2);
    expect(pollMock).not.toHaveBeenCalled();
  });

  it("on resume skips POST if second GET shows day already ready", async () => {
    getTripMock
      .mockResolvedValueOnce({
        trip: trip({ planning_day_index: 1, next_day_index: 1 }),
        route: null,
        days: [day],
      })
      .mockResolvedValueOnce({
        trip: trip({ next_day_index: 2, planning_day_index: null }),
        route: null,
        days: [day],
      });
    const result = await executePlanDayRequest("t1", { resumeDayIndex: 1 });
    expect(planNextDayMock).not.toHaveBeenCalled();
    expect(result.trip.next_day_index).toBe(2);
  });

  it("on resume with stale claim POSTs to reclaim", async () => {
    const startedAt = new Date(Date.now() - 7 * 60 * 1000).toISOString();
    getTripMock
      .mockResolvedValueOnce({
        trip: trip({
          planning_day_index: 1,
          next_day_index: 1,
          planning_started_at: startedAt,
        }),
        route: null,
        days: [],
      })
      .mockResolvedValueOnce({
        trip: trip({
          planning_day_index: 1,
          next_day_index: 1,
          planning_started_at: startedAt,
        }),
        route: null,
        days: [],
      });
    planNextDayMock.mockResolvedValue({
      status: 202,
      trip: trip({ planning_day_index: 1 }),
      planning_day_index: 1,
    });
    pollMock.mockResolvedValue({
      day,
      trip: trip({ next_day_index: 2 }),
    });
    await executePlanDayRequest("t1", { resumeDayIndex: 1 });
    expect(planNextDayMock).toHaveBeenCalledWith("t1");
    expect(pollMock).toHaveBeenCalledWith("t1", 1);
  });
});
