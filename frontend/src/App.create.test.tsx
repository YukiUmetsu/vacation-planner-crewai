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

import {
  confirmCities,
  createTrip,
  getTrip,
  planNextDay,
  proposeCities,
} from "./api/trips";

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

const proposedRoute = {
  destination_type: "country" as const,
  cities: [
    {
      city: "Tokyo",
      nights: 3,
      arrival_day_index: 1,
      departure_day_index: 3,
    },
    {
      city: "Kyoto",
      nights: 3,
      arrival_day_index: 4,
      departure_day_index: 7,
    },
  ],
  total_nights: 6,
  status: "proposed" as const,
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
        screen.getByText(
          (content) =>
            content.includes("New York") && content.includes("Japan"),
        ),
      ).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Review cities/i }));

    expect(
      screen.getByRole("heading", { name: /Add or edit your cities/i }),
    ).toBeInTheDocument();
  });

  it("proposes, confirms cities, and plans the next day", async () => {
    const user = userEvent.setup();
    vi.mocked(createTrip).mockResolvedValue({
      trip: createdTrip,
      route: null,
    });
    vi.mocked(getTrip).mockResolvedValue({
      trip: { ...createdTrip, status: "drafting" },
      route: null,
      days: [],
    });
    vi.mocked(proposeCities).mockResolvedValue({
      trip: { ...createdTrip, status: "awaiting_city_confirm" },
      route: proposedRoute,
    });
    vi.mocked(confirmCities).mockResolvedValue({
      trip: { ...createdTrip, status: "routing_confirmed" },
      route: { ...proposedRoute, status: "confirmed" },
    });
    vi.mocked(planNextDay).mockResolvedValue({
      trip: {
        ...createdTrip,
        status: "planning",
        next_day_index: 2,
      },
      day: {
        day_index: 1,
        date: "2026-08-01",
        theme: "Arrival",
        overnight_city: "Tokyo",
        places: [{ name: "Senso-ji", place_key: "senso-ji" }],
      },
    });

    renderLiveApp();

    await user.click(screen.getByRole("button", { name: "Create trip" }));
    await waitFor(() => expect(getTrip).toHaveBeenCalled());

    await user.click(
      screen.getByRole("button", { name: /Continue to cities/i }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Add or edit your cities/i }),
      ).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Propose cities/i }));
    await waitFor(() => {
      expect(proposeCities).toHaveBeenCalledWith("trip-123");
    });
    await waitFor(() => {
      expect(screen.getByText("Tokyo")).toBeInTheDocument();
      expect(screen.getByText("Kyoto")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Confirm route/i }));
    await waitFor(() => {
      expect(confirmCities).toHaveBeenCalledWith(
        "trip-123",
        expect.objectContaining({
          status: "confirmed",
          cities: expect.arrayContaining([
            expect.objectContaining({ city: "Tokyo" }),
            expect.objectContaining({ city: "Kyoto" }),
          ]),
        }),
      );
    });
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Plan your days/i }),
      ).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Plan next day/i }));
    await waitFor(() => {
      expect(planNextDay).toHaveBeenCalledWith("trip-123");
    });
    await waitFor(() => {
      expect(screen.getByText("Senso-ji")).toBeInTheDocument();
    });
  });
});
