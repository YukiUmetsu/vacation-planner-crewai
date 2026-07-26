import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DaysPanel } from "./DaysPanel";
import type { DayPlan } from "../../types/trip";

afterEach(() => cleanup());

const day1: DayPlan = {
  day_index: 1,
  date: "2026-09-01",
  overnight_city: "Tokyo",
  theme: "Arrival",
  places: [
    {
      name: "Senso-ji",
      place_key: "senso-ji",
      category: "culture",
      order_in_day: 1,
    },
  ],
};

describe("DaysPanel loading", () => {
  it("shows city-focused full loading when planning the first day", () => {
    render(
      <DaysPanel
        days={[]}
        dayCount={5}
        destination="Japan"
        planningCity="Tokyo"
        pending
      />,
    );
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText("Tokyo")).toBeInTheDocument();
    expect(screen.getByText(/gathering places for Tokyo/i)).toBeInTheDocument();
  });

  it("shows inline planning card with city imagery for day 2+", () => {
    render(
      <DaysPanel
        days={[day1]}
        dayCount={5}
        destination="Japan"
        planningCity="Kyoto"
        pending
        onPlanNextDay={() => undefined}
      />,
    );
    expect(screen.getByText(/Planning day 2/i)).toBeInTheDocument();
    expect(screen.getByText("Kyoto")).toBeInTheDocument();
    expect(screen.getByText(/Gathering places for Kyoto/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Planning next day/i })).toBeDisabled();
  });

  it("shows suggest pending strip with overnight city", () => {
    render(
      <DaysPanel
        days={[day1]}
        dayCount={5}
        destination="Japan"
        suggestPendingDay={1}
        onSuggestPlace={() => undefined}
      />,
    );
    expect(screen.getByText("Suggesting a place")).toBeInTheDocument();
    expect(screen.getByText(/Finding a spot in Tokyo/i)).toBeInTheDocument();
  });

  it("disables suggest while day planning is in progress", () => {
    render(
      <DaysPanel
        days={[day1]}
        dayCount={5}
        destination="Japan"
        pending
        onSuggestPlace={() => undefined}
      />,
    );
    expect(
      screen.getByRole("button", { name: /Suggest a place/i }),
    ).toBeDisabled();
  });
});
