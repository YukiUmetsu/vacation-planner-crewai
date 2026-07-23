import { describe, expect, it } from "vitest";
import {
  clampEndDateToStart,
  inclusiveDayCount,
  maxEndDateForStart,
  withEndDateChange,
  withStartDateChange,
} from "./tripDates";

describe("inclusiveDayCount", () => {
  it("counts inclusive calendar days", () => {
    expect(inclusiveDayCount("2026-08-01", "2026-08-01")).toBe(1);
    expect(inclusiveDayCount("2026-08-01", "2026-08-07")).toBe(7);
    expect(inclusiveDayCount("2026-08-01", "2026-08-14")).toBe(14);
    // Aug 1 → Aug 15 looks like “14 days later” on a calendar diff, but is 15 days inclusive.
    expect(inclusiveDayCount("2026-08-01", "2026-08-15")).toBe(15);
  });
});

describe("maxEndDateForStart", () => {
  it("allows at most 14 inclusive days", () => {
    expect(maxEndDateForStart("2026-08-01")).toBe("2026-08-14");
  });
});

describe("clampEndDateToStart", () => {
  it("keeps end when it is on or after start", () => {
    expect(clampEndDateToStart("2026-08-01", "2026-08-07")).toBe("2026-08-07");
    expect(clampEndDateToStart("2026-08-01", "2026-08-01")).toBe("2026-08-01");
  });

  it("bumps end up to start when end is earlier", () => {
    expect(clampEndDateToStart("2026-08-10", "2026-08-07")).toBe("2026-08-10");
  });

  it("clamps end so the trip is at most 14 inclusive days", () => {
    expect(clampEndDateToStart("2026-08-01", "2026-08-15")).toBe("2026-08-14");
    expect(clampEndDateToStart("2026-08-01", "2026-08-20")).toBe("2026-08-14");
  });
});

describe("withStartDateChange", () => {
  it("moves end forward when start passes it", () => {
    const next = withStartDateChange(
      { start_date: "2026-08-01", end_date: "2026-08-07" },
      "2026-08-12",
    );
    expect(next).toEqual({ start_date: "2026-08-12", end_date: "2026-08-12" });
  });

  it("shortens end when start would make the window exceed 14 days", () => {
    const next = withStartDateChange(
      { start_date: "2026-08-01", end_date: "2026-08-14" },
      "2026-08-05",
    );
    expect(next).toEqual({ start_date: "2026-08-05", end_date: "2026-08-14" });
    expect(inclusiveDayCount(next.start_date, next.end_date)).toBe(10);
  });
});

describe("withEndDateChange", () => {
  it("rejects end before start", () => {
    const next = withEndDateChange(
      { start_date: "2026-08-10", end_date: "2026-08-15" },
      "2026-08-05",
    );
    expect(next.end_date).toBe("2026-08-10");
  });

  it("clamps a 15-day inclusive pick down to 14", () => {
    const next = withEndDateChange(
      { start_date: "2026-08-01", end_date: "2026-08-07" },
      "2026-08-15",
    );
    expect(next.end_date).toBe("2026-08-14");
    expect(inclusiveDayCount(next.start_date, next.end_date)).toBe(14);
  });
});
