import { describe, expect, it } from "vitest";
import {
  allocateUniquePlaceKey,
  appendPlaceToDay,
  removeDayFromDays,
  removePlaceAt,
  removePlaceFromDays,
  slugifyPlaceName,
} from "../lib/dayPlaces";
import type { DayPlan } from "../types/trip";

function day(places: DayPlan["places"], dayIndex = 1): DayPlan {
  return {
    day_index: dayIndex,
    date: "2026-08-01",
    theme: "Test",
    overnight_city: "Tokyo",
    places,
  };
}

describe("slugifyPlaceName", () => {
  it("normalizes names to place keys", () => {
    expect(slugifyPlaceName("Shibuya Crossing!")).toBe("shibuya-crossing");
  });
});

describe("allocateUniquePlaceKey", () => {
  it("returns base key when free", () => {
    expect(allocateUniquePlaceKey("Shibuya", ["harajuku"])).toBe("shibuya");
  });

  it("suffixes when base key is taken", () => {
    expect(allocateUniquePlaceKey("Shibuya", ["shibuya"])).toBe("shibuya-2");
    expect(allocateUniquePlaceKey("Shibuya", ["shibuya", "shibuya-2"])).toBe(
      "shibuya-3",
    );
  });
});

describe("removePlaceAt", () => {
  it("removes only the place at the given index", () => {
    const before = day([
      { name: "A", place_key: "dup", order_in_day: 1 },
      { name: "B", place_key: "dup", order_in_day: 2 },
      { name: "C", place_key: "c", order_in_day: 3 },
    ]);

    const after = removePlaceAt(before, 1);

    expect(after.places.map((p) => p.name)).toEqual(["A", "C"]);
    expect(after.places.map((p) => p.order_in_day)).toEqual([1, 2]);
  });

  it("no-ops for out-of-range index", () => {
    const before = day([{ name: "A", place_key: "a", order_in_day: 1 }]);
    expect(removePlaceAt(before, 3)).toBe(before);
    expect(removePlaceAt(before, -1)).toBe(before);
  });
});

describe("removePlaceFromDays", () => {
  it("does not remove places on other days", () => {
    const days = [
      day([{ name: "Tokyo A", place_key: "a" }], 1),
      day([{ name: "Kyoto A", place_key: "a" }], 2),
    ];

    const next = removePlaceFromDays(days, 1, 0);

    expect(next[0]!.places).toHaveLength(0);
    expect(next[1]!.places).toEqual([{ name: "Kyoto A", place_key: "a" }]);
  });
});

describe("removeDayFromDays", () => {
  it("drops only the matching day_index", () => {
    const days = [
      day([{ name: "A", place_key: "a" }], 1),
      day([{ name: "B", place_key: "b" }], 2),
    ];
    expect(removeDayFromDays(days, 1)).toEqual([days[1]]);
  });
});

describe("appendPlaceToDay", () => {
  it("assigns a unique place_key when colliding", () => {
    const before = day([{ name: "Shibuya", place_key: "shibuya" }]);
    const after = appendPlaceToDay(before, {
      name: "Shibuya",
      place_key: "shibuya",
    });

    expect(after.places).toHaveLength(2);
    expect(after.places[1]!.place_key).toBe("shibuya-2");
    expect(after.places[1]!.order_in_day).toBe(2);
  });
});
