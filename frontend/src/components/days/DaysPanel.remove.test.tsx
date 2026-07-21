import { useState } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DaysPanel } from "./DaysPanel";
import { removePlaceFromDays } from "../../lib/dayPlaces";
import type { DayPlan } from "../../types/trip";

afterEach(() => {
  cleanup();
});

function sampleDays(): DayPlan[] {
  return [
    {
      day_index: 1,
      date: "2026-08-01",
      theme: "Neighborhood walks",
      overnight_city: "Tokyo",
      places: [
        { name: "Shibuya", place_key: "shibuya", order_in_day: 1 },
        { name: "Harajuku", place_key: "harajuku", order_in_day: 2 },
        // Duplicate key — old filter-by-key bug would wipe both
        { name: "Shibuya again", place_key: "shibuya", order_in_day: 3 },
      ],
    },
  ];
}

function DaysHarness({
  initialDays = sampleDays(),
  onRemovePlace,
}: {
  initialDays?: DayPlan[];
  onRemovePlace?: (dayIndex: number, placeIndex: number) => void;
}) {
  const [days, setDays] = useState(initialDays);

  return (
    <DaysPanel
      days={days}
      dayCount={7}
      complete
      onRemovePlace={(dayIndex, placeIndex) => {
        onRemovePlace?.(dayIndex, placeIndex);
        setDays((prev) => removePlaceFromDays(prev, dayIndex, placeIndex));
      }}
    />
  );
}

describe("DaysPanel remove", () => {
  it("calls onRemovePlace with day index and place index", async () => {
    const user = userEvent.setup();
    const onRemovePlace = vi.fn();

    render(<DaysHarness onRemovePlace={onRemovePlace} />);

    await user.click(screen.getByRole("button", { name: "Remove Harajuku" }));

    expect(onRemovePlace).toHaveBeenCalledTimes(1);
    expect(onRemovePlace).toHaveBeenCalledWith(1, 1);
  });

  it("removes only the clicked place when place_keys collide", async () => {
    const user = userEvent.setup();
    render(<DaysHarness />);

    await user.click(screen.getByRole("button", { name: "Remove Shibuya" }));

    expect(screen.queryByText("Shibuya")).not.toBeInTheDocument();
    expect(screen.getByText("Shibuya again")).toBeInTheDocument();
    expect(screen.getByText("Harajuku")).toBeInTheDocument();
  });

  it("closes the detail panel when the open place is removed", async () => {
    const user = userEvent.setup();
    render(<DaysHarness />);

    await user.click(screen.getByRole("button", { name: "View Shibuya" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Remove Shibuya" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText("Harajuku")).toBeInTheDocument();
  });
});
