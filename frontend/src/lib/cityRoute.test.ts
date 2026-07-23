import { describe, expect, it } from "vitest";
import {
  addCityStop,
  canAddCityStop,
  maxEditableNights,
  overnightCityForDay,
  recomputeCityDayRanges,
  removeCityAtIndex,
  removeCityByClientId,
  routeWindowIssue,
  setCityNights,
} from "./cityRoute";
import type { CityStop } from "../types/trip";

function stop(
  city: string,
  nights: number,
  extra: Partial<CityStop> = {},
): CityStop {
  return {
    city,
    nights,
    arrival_day_index: 0,
    departure_day_index: 0,
    ...extra,
  };
}

describe("recomputeCityDayRanges", () => {
  it("assigns contiguous day coverage from nights when dayCount is omitted", () => {
    const next = recomputeCityDayRanges([
      stop("Tokyo", 3),
      stop("Kyoto", 2),
      stop("Osaka", 1),
    ]);

    expect(next.map((c) => [c.city, c.arrival_day_index, c.departure_day_index])).toEqual([
      ["Tokyo", 1, 3],
      ["Kyoto", 4, 5],
      ["Osaka", 6, 6],
    ]);
  });

  it("extends the last stop through dayCount for a 7-day / 6-night route", () => {
    const next = recomputeCityDayRanges(
      [stop("Tokyo", 3), stop("Kyoto", 2), stop("Osaka", 1)],
      7,
    );

    expect(next.map((c) => [c.city, c.nights, c.arrival_day_index, c.departure_day_index])).toEqual([
      ["Tokyo", 3, 1, 3],
      ["Kyoto", 2, 4, 5],
      ["Osaka", 1, 6, 7],
    ]);
    expect(overnightCityForDay(next, 7)).toBe("Osaka");
  });

  it("covers a single-city trip through dayCount with nights = dayCount - 1", () => {
    const next = recomputeCityDayRanges([stop("Paris", 1)], 7);
    expect(next[0]).toMatchObject({
      arrival_day_index: 1,
      departure_day_index: 7,
      nights: 6,
    });
    expect(next.reduce((sum, c) => sum + c.nights, 0)).toBe(6);
  });
});

describe("addCityStop", () => {
  it("appends and recomputes coverage from existing nights", () => {
    const base = recomputeCityDayRanges([stop("Tokyo", 3), stop("Kyoto", 2)]);
    const next = addCityStop(base, {
      city: "Hiroshima",
      nights: 1,
      client_id: "c3",
      reason: "day trip vibes",
    });

    expect(next).toHaveLength(3);
    expect(next[2]).toMatchObject({
      city: "Hiroshima",
      arrival_day_index: 6,
      departure_day_index: 6,
      client_id: "c3",
    });
  });

  it("extends the new last city to dayCount", () => {
    // Prior stops without a window; adding Osaka as last fills through day 7.
    const base = recomputeCityDayRanges([stop("Tokyo", 3), stop("Kyoto", 2)]);
    const next = addCityStop(
      base,
      { city: "Osaka", nights: 1, client_id: "c3" },
      7,
    );
    expect(next[2]).toMatchObject({
      city: "Osaka",
      nights: 1,
      arrival_day_index: 6,
      departure_day_index: 7,
    });
    expect(next.reduce((sum, c) => sum + c.nights, 0)).toBe(6);
  });
});

describe("setCityNights", () => {
  it("updates nights and shifts later cities", () => {
    const base = recomputeCityDayRanges([
      stop("Tokyo", 3),
      stop("Kyoto", 2),
    ]);
    const next = setCityNights(base, 0, 5);

    expect(next[0]).toMatchObject({
      city: "Tokyo",
      nights: 5,
      arrival_day_index: 1,
      departure_day_index: 5,
    });
    expect(next[1]).toMatchObject({
      city: "Kyoto",
      arrival_day_index: 6,
      departure_day_index: 7,
    });
  });

  it("keeps last departure on dayCount after nights edits", () => {
    const base = recomputeCityDayRanges(
      [stop("Tokyo", 3), stop("Kyoto", 2), stop("Osaka", 1)],
      7,
    );
    const next = setCityNights(base, 1, 3, 7);
    expect(next.map((c) => [c.city, c.nights, c.arrival_day_index, c.departure_day_index])).toEqual([
      ["Tokyo", 3, 1, 3],
      ["Kyoto", 3, 4, 6],
      ["Osaka", 0, 7, 7],
    ]);
    expect(next.reduce((sum, c) => sum + c.nights, 0)).toBe(6);
  });
});

describe("removeCityByClientId", () => {
  it("removes only the matching inserted city when names collide", () => {
    const cities = recomputeCityDayRanges([
      stop("Tokyo", 2, { client_id: "a" }),
      stop("Tokyo", 1, { client_id: "b" }),
      stop("Kyoto", 2, { client_id: "c" }),
    ]);

    const next = removeCityByClientId(cities, "b");

    expect(next.map((c) => c.client_id)).toEqual(["a", "c"]);
    expect(next.map((c) => [c.city, c.arrival_day_index, c.departure_day_index])).toEqual([
      ["Tokyo", 1, 2],
      ["Kyoto", 3, 4],
    ]);
  });

  it("re-extends the new last city to dayCount after remove", () => {
    const cities = recomputeCityDayRanges(
      [
        stop("Tokyo", 3, { client_id: "a" }),
        stop("Kyoto", 2, { client_id: "b" }),
        stop("Osaka", 1, { client_id: "c" }),
      ],
      7,
    );
    const next = removeCityByClientId(cities, "c", 7);
    expect(next.map((c) => [c.city, c.nights, c.arrival_day_index, c.departure_day_index])).toEqual([
      ["Tokyo", 3, 1, 3],
      ["Kyoto", 3, 4, 7],
    ]);
    expect(next.reduce((sum, c) => sum + c.nights, 0)).toBe(6);
  });
});

describe("removeCityAtIndex", () => {
  it("removes by index and recomputes day windows", () => {
    const cities = recomputeCityDayRanges(
      [stop("Tokyo", 3), stop("Kyoto", 2), stop("Osaka", 1)],
      7,
    );
    const next = removeCityAtIndex(cities, 1, 7);
    expect(next.map((c) => c.city)).toEqual(["Tokyo", "Osaka"]);
    expect(next.map((c) => [c.city, c.nights, c.arrival_day_index, c.departure_day_index])).toEqual([
      ["Tokyo", 3, 1, 3],
      ["Osaka", 3, 4, 7],
    ]);
  });
});

describe("maxEditableNights and routeWindowIssue", () => {
  it("caps non-last nights so the window still fits", () => {
    const cities = recomputeCityDayRanges(
      [stop("Tokyo", 3), stop("Kyoto", 2), stop("Osaka", 1)],
      7,
    );
    expect(maxEditableNights(cities, 0, 7)).toBe(4); // 6 expected − 2 Kyoto
    expect(maxEditableNights(cities, 2, 7)).toBe(1); // last locked to current
    expect(canAddCityStop(cities, 7)).toBe(true);
    expect(canAddCityStop(cities, 3)).toBe(false);
  });

  it("setCityNights refuses to overflow the trip window", () => {
    const cities = recomputeCityDayRanges(
      [stop("Tokyo", 3), stop("Kyoto", 2), stop("Osaka", 1)],
      7,
    );
    const next = setCityNights(cities, 0, 99, 7);
    expect(next[0]!.nights).toBe(4);
    expect(routeWindowIssue(next, 7)).toBeNull();
  });

  it("reports a clear issue when too many cities for the window", () => {
    const cities = recomputeCityDayRanges(
      [stop("A", 1), stop("B", 1), stop("C", 1), stop("D", 1)],
      3,
    );
    expect(routeWindowIssue(cities, 3)).toMatch(/at most 3 cities/i);
  });
});

describe("overnightCityForDay", () => {
  it("resolves overnight city from recomputed ranges", () => {
    const cities = recomputeCityDayRanges([
      stop("Tokyo", 3),
      stop("Kyoto", 2),
    ]);
    expect(overnightCityForDay(cities, 1)).toBe("Tokyo");
    expect(overnightCityForDay(cities, 4)).toBe("Kyoto");
    expect(overnightCityForDay(cities, 9)).toBeUndefined();
  });
});
