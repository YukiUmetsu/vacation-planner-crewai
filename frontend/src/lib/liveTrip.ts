import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import {
  confirmCities,
  getTrip,
  planNextDay,
  proposeCities,
  suggestPlace,
} from "../api/trips";
import type { CityStop, DayPlan, Route, Trip, TripBundle } from "../types/trip";
import type { SetStateAction } from "react";
import { pollUntilDayReady } from "./pollPlanDay";

export type LiveTripState = {
  trip: Trip | null;
  cities: CityStop[];
  days: DayPlan[];
  routeMeta: Pick<Route, "destination_type" | "rationale" | "status"> | null;
};

export function emptyLiveTripState(): LiveTripState {
  return { trip: null, cities: [], days: [], routeMeta: null };
}

export function applyTripBundle(bundle: TripBundle): LiveTripState {
  const cities = bundle.route?.cities.map((c) => ({ ...c })) ?? [];
  const days = bundle.days.map((d) => ({
    ...d,
    places: d.places.map((p) => ({ ...p })),
  }));
  const routeMeta = bundle.route
    ? {
        destination_type: bundle.route.destination_type,
        rationale: bundle.route.rationale,
        status: bundle.route.status,
      }
    : null;
  return { trip: bundle.trip, cities, days, routeMeta };
}

export function buildConfirmRoute(
  state: LiveTripState,
  cities: CityStop[],
): Route {
  const destination_type =
    state.routeMeta?.destination_type ??
    state.trip?.destination_type ??
    "country";
  return {
    destination_type,
    cities,
    rationale: state.routeMeta?.rationale,
    total_nights: cities.reduce((sum, c) => sum + c.nights, 0),
    status: "confirmed",
  };
}

/** True when trip has an in-flight plan-next-day the UI should resume polling for. */
export function pendingPlanningDayIndex(
  trip: Trip | null | undefined,
  _days: DayPlan[],
): number | null {
  const pdi = trip?.planning_day_index;
  if (pdi == null) return null;
  const index = Number(pdi);
  if (!Number.isFinite(index) || index < 1) return null;
  // Resume even if DAY already appears — cursor may still need completion.
  return index;
}

type LiveTripActionsArgs = {
  tripId: string | null;
  /** Functional updater so mutation success never stomps concurrent local edits. */
  onApplied: (updater: SetStateAction<LiveTripState>) => void;
  onActionError: (message: string | null) => void;
};

type PlanDayVars = { id: string; resumeDayIndex?: number };

function invalidateTrip(queryClient: QueryClient, id: string) {
  void queryClient.invalidateQueries({ queryKey: ["trip", id] });
}

/** Mutations for live propose / confirm / plan-next-day against the BFF. */
export function useLiveTripActions({
  tripId,
  onApplied,
  onActionError,
}: LiveTripActionsArgs) {
  const queryClient = useQueryClient();

  const proposeMutation = useMutation({
    mutationFn: (id: string) => proposeCities(id),
    onSuccess: (data, id) => {
      onActionError(null);
      onApplied((prev) =>
        applyTripBundle({
          trip: data.trip,
          route: data.route,
          days: prev.days,
        }),
      );
      invalidateTrip(queryClient, id);
    },
    onError: (err: Error) => onActionError(err.message),
  });

  const confirmMutation = useMutation({
    mutationFn: ({ id, route }: { id: string; route: Route }) =>
      confirmCities(id, route),
    onSuccess: (data, { id }) => {
      onActionError(null);
      onApplied((prev) =>
        applyTripBundle({
          trip: data.trip,
          route: data.route,
          days: prev.days,
        }),
      );
      invalidateTrip(queryClient, id);
    },
    onError: (err: Error) => onActionError(err.message),
  });

  const planDayMutation = useMutation({
    mutationFn: async ({ id, resumeDayIndex }: PlanDayVars) => {
      // On resume (refresh), POST again so the BFF can finalize a stuck DAY+claim.
      if (resumeDayIndex != null) {
        try {
          const started = await planNextDay(id);
          if (started.status === 200) {
            return { day: started.day, trip: started.trip };
          }
          onApplied((prev) => ({ ...prev, trip: started.trip }));
          return pollUntilDayReady(id, started.planning_day_index);
        } catch {
          return pollUntilDayReady(id, resumeDayIndex);
        }
      }
      const started = await planNextDay(id);
      if (started.status === 200) {
        return { day: started.day, trip: started.trip };
      }
      onApplied((prev) => ({
        ...prev,
        trip: started.trip,
      }));
      return pollUntilDayReady(id, started.planning_day_index);
    },
    onSuccess: (data, { id }) => {
      onActionError(null);
      const day = data.day;
      onApplied((prev) => {
        const nextDays = [
          ...prev.days.filter((d) => d.day_index !== day.day_index),
          day,
        ].sort((a, b) => a.day_index - b.day_index);
        return {
          ...prev,
          trip: data.trip,
          days: nextDays,
        };
      });
      invalidateTrip(queryClient, id);
    },
    onError: (err: Error) => onActionError(err.message),
  });

  const suggestPlaceMutation = useMutation({
    mutationFn: ({ id, dayIndex }: { id: string; dayIndex: number }) =>
      suggestPlace(id, dayIndex),
    onSuccess: (data, { id }) => {
      onActionError(null);
      const day = data.day;
      onApplied((prev) => {
        const nextDays = [
          ...prev.days.filter((d) => d.day_index !== day.day_index),
          day,
        ].sort((a, b) => a.day_index - b.day_index);
        return {
          ...prev,
          trip: data.trip,
          days: nextDays,
        };
      });
      invalidateTrip(queryClient, id);
    },
    onError: (err: Error) => onActionError(err.message),
  });

  async function hydrateFromApi(id: string) {
    const bundle = await getTrip(id);
    onApplied(applyTripBundle(bundle));
    const resume = pendingPlanningDayIndex(bundle.trip, bundle.days);
    if (resume != null && !planDayMutation.isPending) {
      planDayMutation.mutate({ id, resumeDayIndex: resume });
    }
    return bundle;
  }

  function runPropose() {
    if (!tripId) return;
    proposeMutation.mutate(tripId);
  }

  function runConfirm(route: Route) {
    if (!tripId) return;
    confirmMutation.mutate({ id: tripId, route });
  }

  function runPlanNextDay() {
    if (!tripId) return;
    planDayMutation.mutate({ id: tripId });
  }

  function runSuggestPlace(dayIndex: number) {
    if (!tripId) return;
    suggestPlaceMutation.mutate({ id: tripId, dayIndex });
  }

  return {
    proposeMutation,
    confirmMutation,
    planDayMutation,
    suggestPlaceMutation,
    hydrateFromApi,
    runPropose,
    runConfirm,
    runPlanNextDay,
    runSuggestPlace,
  };
}
