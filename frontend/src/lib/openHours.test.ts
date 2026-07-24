import { describe, expect, it } from "vitest";
import { parseOpenHours } from "./openHours";

describe("parseOpenHours", () => {
  it("splits Google semicolon weekday blob into day rows", () => {
    const rows = parseOpenHours(
      "Monday: 11:00 AM – 3:00 PM; Tuesday: Closed; Wednesday: 11:00 AM – 3:00 PM; Thursday: 11:00 AM – 3:00 PM; Friday: 11:00 AM – 3:00 PM; Saturday: 11:00 AM – 3:00 PM; Sunday: 11:00 AM – 3:00 PM",
    );
    expect(rows).toHaveLength(7);
    expect(rows[0]).toEqual({ day: "Monday", hours: "11:00 AM – 3:00 PM" });
    expect(rows[1]).toEqual({ day: "Tuesday", hours: "Closed" });
    expect(rows[6]?.day).toBe("Sunday");
  });

  it("handles Open 24 hours", () => {
    expect(parseOpenHours("Open 24 hours")).toEqual([
      { day: "Every day", hours: "Open 24 hours" },
    ]);
  });

  it("falls back to a single row for free text", () => {
    expect(parseOpenHours("Shops ~10:00–18:00")).toEqual([
      { day: "Hours", hours: "Shops ~10:00–18:00" },
    ]);
  });
});
