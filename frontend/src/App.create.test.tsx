import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { Trip, TripBundle } from "./types/trip";

vi.mock("./api/trips", () => ({
  createTrip: vi.fn(),
  updateTrip: vi.fn(),
  listTrips: vi.fn(),
  getTrip: vi.fn(),
  deleteTrip: vi.fn(),
  proposeCities: vi.fn(),
  confirmCities: vi.fn(),
  planNextDay: vi.fn(),
}));

import {
  confirmCities,
  createTrip,
  deleteTrip,
  getTrip,
  listTrips,
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

beforeEach(() => {
  vi.mocked(listTrips).mockResolvedValue({ trips: [] });
});

const createdTrip: Trip = {
  trip_id: "trip-123",
  origin: "New York",
  destination: "Japan",
  destination_type: "country",
  start_date: "2026-08-01",
  end_date: "2026-08-07",
  day_count: 7,
  preferences: "food",
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

const draftBundle: TripBundle = {
  trip: { ...createdTrip, status: "draft" },
  route: null,
  days: [],
};

describe("App live create flow", () => {
  it("keeps Create disabled while hydrate runs and rejects a second submit", async () => {
    const user = userEvent.setup();
    let resolveGetTrip!: (value: TripBundle) => void;
    const deferredGetTrip = new Promise<TripBundle>((resolve) => {
      resolveGetTrip = resolve;
    });

    vi.mocked(createTrip).mockResolvedValue({
      trip: createdTrip,
      route: null,
    });
    // One shared promise so TripPanel + hydrate both wait (and teardown can finish).
    vi.mocked(getTrip).mockImplementation(() => deferredGetTrip);
    vi.mocked(proposeCities).mockResolvedValue({
      trip: { ...createdTrip, status: "awaiting_city_confirm" },
      route: proposedRoute,
    });

    renderLiveApp();

    const submit = screen.getByRole("button", { name: "Create trip" });
    await user.click(submit);

    await waitFor(() => {
      expect(createTrip).toHaveBeenCalledTimes(1);
      expect(getTrip).toHaveBeenCalledWith("trip-123");
    });

    const busy = screen.getByRole("button", { name: /Creating/i });
    expect(busy).toBeDisabled();

    await user.click(busy);
    expect(createTrip).toHaveBeenCalledTimes(1);
    expect(proposeCities).not.toHaveBeenCalled();

    resolveGetTrip(draftBundle);
    await waitFor(() => {
      expect(proposeCities).toHaveBeenCalledWith("trip-123");
    });
    expect(createTrip).toHaveBeenCalledTimes(1);
  });

  it("creates a trip and immediately starts proposing cities", async () => {
    const user = userEvent.setup();
    vi.mocked(createTrip).mockResolvedValue({
      trip: createdTrip,
      route: null,
    });
    vi.mocked(getTrip).mockResolvedValue(draftBundle);
    vi.mocked(proposeCities).mockImplementation(
      () =>
        new Promise(() => {
          /* keep pending so loading UI stays visible */
        }),
    );

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
      expect(proposeCities).toHaveBeenCalledWith("trip-123");
    });
    await waitFor(() => {
      expect(screen.getByText(/Sketching your route/i)).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Japan" })).toBeInTheDocument();
    });
  });

  it("proposes, confirms cities, and auto-plans the first day", async () => {
    const user = userEvent.setup();
    let proposeResolve: ((value: {
      trip: Trip;
      route: typeof proposedRoute;
    }) => void) | null = null;

    vi.mocked(createTrip).mockResolvedValue({
      trip: createdTrip,
      route: null,
    });
    vi.mocked(getTrip).mockResolvedValue(draftBundle);
    vi.mocked(proposeCities).mockImplementation(
      () =>
        new Promise((resolve) => {
          proposeResolve = resolve;
        }),
    );
    vi.mocked(confirmCities).mockResolvedValue({
      trip: { ...createdTrip, status: "routing_confirmed" },
      route: { ...proposedRoute, status: "confirmed" },
    });
    vi.mocked(planNextDay).mockResolvedValue({
      status: 200,
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
    await waitFor(() => expect(proposeCities).toHaveBeenCalled());

    await waitFor(() => {
      expect(proposeResolve).not.toBeNull();
    });
    proposeResolve!({
      trip: { ...createdTrip, status: "awaiting_city_confirm" },
      route: proposedRoute,
    });

    await waitFor(() => {
      expect(screen.getByText("Tokyo")).toBeInTheDocument();
      expect(screen.getByText("Kyoto")).toBeInTheDocument();
    });

    expect(
      screen.getByRole("button", { name: /Remove Tokyo from route/i }),
    ).toBeInTheDocument();

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
    await waitFor(() => {
      expect(planNextDay).toHaveBeenCalledWith("trip-123");
    });
    await waitFor(() => {
      expect(screen.getByText("Senso-ji")).toBeInTheDocument();
    });
  });

  it("lets the traveler go back from cities to edit trip details", async () => {
    const user = userEvent.setup();
    vi.mocked(createTrip).mockResolvedValue({
      trip: createdTrip,
      route: null,
    });
    vi.mocked(getTrip).mockResolvedValue({
      trip: { ...createdTrip, status: "awaiting_city_confirm" },
      route: proposedRoute,
      days: [],
    });
    vi.mocked(proposeCities).mockResolvedValue({
      trip: { ...createdTrip, status: "awaiting_city_confirm" },
      route: proposedRoute,
    });

    renderLiveApp();

    await user.click(screen.getByRole("button", { name: "Create trip" }));
    await waitFor(() => {
      expect(screen.getByText("Tokyo")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Trip details/i }));
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Edit trip details/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Save & re-propose cities/i }),
      ).toBeInTheDocument();
    });
  });

  it("resumes the latest incomplete trip on details and lists all trips", async () => {
    const older: Trip = {
      ...createdTrip,
      trip_id: "trip-old",
      destination: "Italy",
      status: "complete",
      created_at: "2026-01-01T00:00:00Z",
    };
    const open: Trip = {
      ...createdTrip,
      trip_id: "trip-open",
      destination: "Japan",
      status: "planning",
      created_at: "2026-06-01T00:00:00Z",
    };
    vi.mocked(listTrips).mockResolvedValue({ trips: [open, older] });
    vi.mocked(getTrip).mockResolvedValue({
      trip: open,
      route: { ...proposedRoute, status: "confirmed" },
      days: [],
    });

    renderLiveApp();

    await waitFor(() => {
      expect(listTrips).toHaveBeenCalled();
      expect(getTrip).toHaveBeenCalledWith("trip-open");
    });
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Edit trip details/i }),
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^Japan/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^Italy/i })).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Remove Japan/i }),
      ).toBeInTheDocument();
    });
  });

  it("auto-starts day planning when opening Days on an old trip with no days", async () => {
    const user = userEvent.setup();
    const open: Trip = {
      ...createdTrip,
      trip_id: "trip-open",
      status: "routing_confirmed",
      created_at: "2026-06-01T00:00:00Z",
    };
    vi.mocked(listTrips).mockResolvedValue({ trips: [open] });
    vi.mocked(getTrip).mockResolvedValue({
      trip: open,
      route: { ...proposedRoute, status: "confirmed" },
      days: [],
    });
    vi.mocked(planNextDay).mockResolvedValue({
      status: 200,
      trip: { ...open, status: "planning", next_day_index: 2 },
      day: {
        day_index: 1,
        date: "2026-08-01",
        theme: "Arrival",
        overnight_city: "Tokyo",
        places: [{ name: "Senso-ji", place_key: "senso-ji" }],
      },
    });

    renderLiveApp();

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Edit trip details/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Continue to days/i }),
      ).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Continue to days/i }));

    await waitFor(() => {
      expect(planNextDay).toHaveBeenCalledWith("trip-open");
    });
    await waitFor(() => {
      expect(screen.getByText("Senso-ji")).toBeInTheDocument();
    });
  });

  it("removes a trip after confirm and loads the next incomplete one", async () => {
    const user = userEvent.setup();
    const open: Trip = {
      ...createdTrip,
      trip_id: "trip-open",
      destination: "Japan",
      status: "planning",
      created_at: "2026-06-01T00:00:00Z",
    };
    const other: Trip = {
      ...createdTrip,
      trip_id: "trip-other",
      destination: "Spain",
      status: "drafting",
      created_at: "2026-05-01T00:00:00Z",
    };
    vi.mocked(listTrips).mockResolvedValue({ trips: [open, other] });
    vi.mocked(getTrip).mockImplementation(async (id: string) => ({
      trip: id === "trip-other" ? other : open,
      route: null,
      days: [],
    }));
    vi.mocked(deleteTrip).mockResolvedValue({
      ok: true,
      trip_id: "trip-open",
      deleted: { TRIP: 1, ROUTE: 0, DAY: 0, total: 1 },
    });

    renderLiveApp();

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Edit trip details/i }),
      ).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Remove Japan/i }));
    await user.click(screen.getByRole("button", { name: /^Remove$/i }));

    await waitFor(() => {
      expect(deleteTrip).toHaveBeenCalledWith("trip-open");
      expect(getTrip).toHaveBeenCalledWith("trip-other");
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Spain/i })).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /^Japan/i }),
      ).not.toBeInTheDocument();
    });
  });

  it("unlocks top nav steps as the trip progresses", async () => {
    const user = userEvent.setup();
    const proposedBundle: TripBundle = {
      trip: { ...createdTrip, status: "awaiting_city_confirm" },
      route: proposedRoute,
      days: [],
    };
    const confirmedBundle: TripBundle = {
      trip: { ...createdTrip, status: "routing_confirmed" },
      route: { ...proposedRoute, status: "confirmed" },
      days: [],
    };

    vi.mocked(createTrip).mockResolvedValue({
      trip: createdTrip,
      route: null,
    });
    vi.mocked(getTrip).mockResolvedValue(proposedBundle);
    vi.mocked(proposeCities).mockResolvedValue({
      trip: proposedBundle.trip,
      route: proposedRoute,
    });
    vi.mocked(confirmCities).mockResolvedValue({
      trip: confirmedBundle.trip,
      route: confirmedBundle.route!,
    });
    vi.mocked(planNextDay).mockResolvedValue({
      status: 200,
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

    const stepNav = () => screen.getByRole("navigation", { name: "Trip steps" });
    const detailsNav = () =>
      within(stepNav()).getByRole("button", { name: /Details/i });
    const citiesNav = () =>
      within(stepNav()).getByRole("button", { name: /Cities/i });
    const daysNav = () =>
      within(stepNav()).getByRole("button", { name: /Days/i });

    expect(detailsNav()).toBeEnabled();
    expect(citiesNav()).toBeDisabled();
    expect(daysNav()).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Create trip" }));
    await waitFor(() => {
      expect(screen.getByText("Tokyo")).toBeInTheDocument();
    });

    expect(detailsNav()).toBeEnabled();
    expect(citiesNav()).toBeEnabled();
    expect(daysNav()).toBeDisabled();

    await user.click(detailsNav());
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Edit trip details/i }),
      ).toBeInTheDocument();
    });

    await user.click(citiesNav());
    await waitFor(() => {
      expect(screen.getByText("Tokyo")).toBeInTheDocument();
    });

    vi.mocked(getTrip).mockResolvedValue(confirmedBundle);

    await user.click(screen.getByRole("button", { name: /Confirm route/i }));
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Plan your days/i }),
      ).toBeInTheDocument();
    });

    expect(daysNav()).toBeEnabled();

    await user.click(detailsNav());
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Edit trip details/i }),
      ).toBeInTheDocument();
    });

    await user.click(daysNav());
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Plan your days/i }),
      ).toBeInTheDocument();
    });
  });
});
