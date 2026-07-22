import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DaysPanel } from "./DaysPanel";
import type { DayPlan } from "../../types/trip";

afterEach(() => {
  cleanup();
});

function heavyDay(): DayPlan[] {
  return [
    {
      day_index: 1,
      date: "2026-08-01",
      theme: "Packed",
      overnight_city: "Tokyo",
      places: [
        {
          name: "A",
          place_key: "a",
          estimated_minutes: 120,
          order_in_day: 1,
        },
        {
          name: "B",
          place_key: "b",
          estimated_minutes: 120,
          order_in_day: 2,
          travel_minutes_from_previous: 30,
        },
        {
          name: "C",
          place_key: "c",
          estimated_minutes: 120,
          order_in_day: 3,
          travel_minutes_from_previous: 30,
        },
      ],
    },
  ];
}

describe("DaysPanel energy warning", () => {
  it("warns when low energy and the day is overloaded", () => {
    render(
      <DaysPanel
        days={heavyDay()}
        dayCount={1}
        energyLevel={1}
        complete
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/energy load/i);
    expect(screen.getByRole("status")).toHaveTextContent(/level 1/i);
  });

  it("stays quiet for high energy on the same day", () => {
    render(
      <DaysPanel
        days={heavyDay()}
        dayCount={1}
        energyLevel={5}
        complete
      />,
    );
    expect(screen.queryByText(/energy load/i)).toBeNull();
  });
});
