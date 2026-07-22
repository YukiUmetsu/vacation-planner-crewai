import { describe, expect, it } from "vitest";
import {
  assessDayEnergyLoad,
  clampEnergyLevel,
  MAX_COMFORTABLE_TOTAL_MINUTES,
} from "./energyLevel";

describe("clampEnergyLevel", () => {
  it("clamps to 1..5", () => {
    expect(clampEnergyLevel(0)).toBe(1);
    expect(clampEnergyLevel(1)).toBe(1);
    expect(clampEnergyLevel(3.4)).toBe(3);
    expect(clampEnergyLevel(5)).toBe(5);
    expect(clampEnergyLevel(9)).toBe(5);
  });

  it("defaults non-finite values to moderate (3)", () => {
    expect(clampEnergyLevel(Number.NaN)).toBe(3);
    expect(clampEnergyLevel(Number.POSITIVE_INFINITY)).toBe(3);
    expect(clampEnergyLevel(Number.NEGATIVE_INFINITY)).toBe(3);
  });
});

describe("assessDayEnergyLoad", () => {
  it("is ok under the comfort cap", () => {
    const load = assessDayEnergyLoad(3, MAX_COMFORTABLE_TOTAL_MINUTES[3]);
    expect(load.severity).toBe("ok");
    expect(load.message).toBeNull();
  });

  it("cautions slightly over the cap", () => {
    const cap = MAX_COMFORTABLE_TOTAL_MINUTES[2];
    const load = assessDayEnergyLoad(2, cap + 30);
    expect(load.severity).toBe("caution");
    expect(load.overByMinutes).toBe(30);
    expect(load.message).toMatch(/energy level 2/i);
  });

  it("flags overloaded days for low energy", () => {
    const cap = MAX_COMFORTABLE_TOTAL_MINUTES[1];
    const load = assessDayEnergyLoad(1, Math.ceil(cap * 1.5));
    expect(load.severity).toBe("overloaded");
    expect(load.message).toMatch(/too full|exceeds/i);
  });

  it("allows high-energy travelers longer days", () => {
    const load = assessDayEnergyLoad(5, 500);
    expect(load.severity).toBe("ok");
  });
});
