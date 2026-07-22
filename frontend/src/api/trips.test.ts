import { beforeEach, describe, expect, it, vi } from "vitest";
import { confirmCities, routeForConfirmRequest } from "./trips";
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
