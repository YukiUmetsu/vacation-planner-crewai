import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { Trip, TripBundle } from "./types/trip";

vi.mock("./api/trips", () => ({
  createTrip: vi.fn(),
  getTrip: vi.fn(),
  proposeCities: vi.fn(),
  confirmCities: vi.fn(),
  planNextDay: vi.fn(),
}));

import { createTrip, getTrip } from "./api/trips";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderLiveApp() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <App demoMode={false} />
    </QueryClientProvider>,
  );
}

const createdTrip: Trip = {
  trip_id: "trip-123",
  origin: "New York",
  destination: "Japan",
  destination_type: "country",
  start_date: "2026-08-01",
  end_date: "2026-08-07",
  day_count: 7,
  preferences: "food and trains",
  status: "draft",
};

const bundle: TripBundle = {
  trip: { ...createdTrip, status: "routing_proposed" },
  route: {
    destination_type: "country",
    cities: [
      {
        city: "Tokyo",
        nights: 3,
        arrival_day_index: 1,
        departure_day_index: 3,
      },
    ],
    total_nights: 3,
    status: "proposed",
  },
  days: [],
};

describe("App live create flow", () => {
  it("stores trip id, shows TripPanel gist, and advances wizard", async () => {
    const user = userEvent.setup();
    vi.mocked(createTrip).mockResolvedValue({
      trip: createdTrip,
      route: null,
    });
    vi.mocked(getTrip).mockResolvedValue(bundle);

    renderLiveApp();

    expect(
      screen.getByText(/Your itinerary appears here/i),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Create trip" }));

    await waitFor(() => {
      expect(createTrip).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(getTrip).toHaveBeenCalledWith("trip-123");
    });

    await waitFor(() => {
      expect(
        screen.getByText((content) => content.includes("New York") && content.includes("Japan")),
      ).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Review cities/i }));

    expect(
      screen.getByRole("heading", { name: /Add or edit your cities/i }),
    ).toBeInTheDocument();
  });
});
