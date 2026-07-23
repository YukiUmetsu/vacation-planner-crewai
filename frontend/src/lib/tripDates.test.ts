import { describe, expect, it } from "vitest";
import {
  clampEndDateToStart,
  withEndDateChange,
  withStartDateChange,
} from "./tripDates";

describe("clampEndDateToStart", () => {
  it("keeps end when it is on or after start", () => {
    expect(clampEndDateToStart("2026-08-01", "2026-08-07")).toBe("2026-08-07");
    expect(clampEndDateToStart("2026-08-01", "2026-08-01")).toBe("2026-08-01");
  });

  it("bumps end up to start when end is earlier", () => {
    expect(clampEndDateToStart("2026-08-10", "2026-08-07")).toBe("2026-08-10");
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
});

describe("withEndDateChange", () => {
  it("rejects end before start", () => {
    const next = withEndDateChange(
      { start_date: "2026-08-10", end_date: "2026-08-15" },
      "2026-08-05",
    );
    expect(next.end_date).toBe("2026-08-10");
  });
});
