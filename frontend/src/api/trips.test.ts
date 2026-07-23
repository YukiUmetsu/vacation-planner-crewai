import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  confirmCities,
  deleteTrip,
  listTrips,
  planNextDay,
  routeForConfirmRequest,
} from "./trips";
import type { Route } from "../types/trip";

const sampleRoute: Route = {
  destination_type: "country",
  total_nights: 3,
  status: "proposed",
  rationale: "demo",
  cities: [
    {
      city: "Tokyo",
      nights: 2,
      arrival_day_index: 1,
      departure_day_index: 2,
      client_id: "fe-only-1",
    },
    {
      city: "Kyoto",
      nights: 1,
      arrival_day_index: 3,
      departure_day_index: 3,
      client_id: "fe-only-2",
    },
  ],
};

describe("routeForConfirmRequest", () => {
  it("strips client_id from every city", () => {
    const body = routeForConfirmRequest(sampleRoute);
    expect(body.status).toBe("confirmed");
    expect(body.cities).toEqual([
      {
        city: "Tokyo",
        nights: 2,
        arrival_day_index: 1,
        departure_day_index: 2,
      },
      {
        city: "Kyoto",
        nights: 1,
        arrival_day_index: 3,
        departure_day_index: 3,
      },
    ]);
    for (const city of body.cities as Record<string, unknown>[]) {
      expect(city).not.toHaveProperty("client_id");
    }
  });
});

describe("listTrips", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    vi.stubEnv("DEV", true);
    vi.stubEnv("VITE_API_URL", "");
  });

  it("GETs /trips and returns the trips array payload", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          trips: [
            {
              trip_id: "t1",
              origin: "NYC",
              destination: "Japan",
              destination_type: "country",
              start_date: "2026-08-01",
              end_date: "2026-08-07",
              day_count: 7,
              status: "drafting",
            },
          ],
        }),
        { status: 200 },
      ),
    );

    const result = await listTrips();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/trips",
      expect.objectContaining({ method: "GET" }),
    );
    expect(result.trips).toHaveLength(1);
    expect(result.trips[0]?.trip_id).toBe("t1");
  });
});

describe("deleteTrip", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    vi.stubEnv("DEV", true);
    vi.stubEnv("VITE_API_URL", "");
  });

  it("DELETEs /trips/{id}", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          trip_id: "t1",
          deleted: { TRIP: 1, ROUTE: 1, DAY: 1, total: 3 },
        }),
        { status: 200 },
      ),
    );

    const result = await deleteTrip("t1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/trips/t1",
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(result).toEqual({
      ok: true,
      trip_id: "t1",
      deleted: { TRIP: 1, ROUTE: 1, DAY: 1, total: 3 },
    });
  });
});

describe("confirmCities", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    vi.stubEnv("DEV", true);
    vi.stubEnv("VITE_API_URL", "");
  });

  it("PUTs a body without client_id fields", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ trip: {}, route: null }), { status: 200 }),
    );

    await confirmCities("trip-1", sampleRoute);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/trips/trip-1/cities",
      expect.objectContaining({ method: "PUT" }),
    );
    const init = fetchMock.mock.calls[0]![1];
    const parsed = JSON.parse(String(init?.body)) as {
      cities: Record<string, unknown>[];
      status: string;
    };
    expect(parsed.status).toBe("confirmed");
    expect(parsed.cities).toHaveLength(2);
    for (const city of parsed.cities) {
      expect(city).not.toHaveProperty("client_id");
      expect(city.city).toBeTruthy();
    }
  });
});

describe("planNextDay", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    vi.stubEnv("DEV", true);
    vi.stubEnv("VITE_API_URL", "");
  });

  it("discriminates sync 200 vs async 202", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          day: {
            day_index: 1,
            date: "2026-08-01",
            theme: "A",
            overnight_city: "Tokyo",
            places: [],
          },
          trip: { trip_id: "t1", status: "planning", next_day_index: 2 },
        }),
        { status: 200 },
      ),
    );
    const sync = await planNextDay("t1");
    expect(sync.status).toBe(200);
    if (sync.status === 200) {
      expect(sync.day.day_index).toBe(1);
    }

    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          trip: { trip_id: "t1", status: "planning", planning_day_index: 1 },
          planning_day_index: 1,
        }),
        { status: 202 },
      ),
    );
    const asyncResult = await planNextDay("t1");
    expect(asyncResult.status).toBe(202);
    if (asyncResult.status === 202) {
      expect(asyncResult.planning_day_index).toBe(1);
    }
  });
});
