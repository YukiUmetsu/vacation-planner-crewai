import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import {
  confirmCities,
  deleteDay,
  getTrip,
  proposeCities,
  removePlace,
  suggestPlace,
} from "../api/trips";
import type { CityStop, DayPlan, Route, Trip, TripBundle } from "../types/trip";
import { useRef, type SetStateAction } from "react";
import { executePlanDayRequest } from "./executePlanDayRequest";

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
  /** Bumped to ignore stale propose responses after cancel / replace. */
  const proposeEpochRef = useRef(0);
  /** Bumped to ignore stale plan-next-day updates after trip switch. */
  const planEpochRef = useRef(0);
  /** Bumped to ignore stale getTrip hydrations after trip switch. */
  const hydrateEpochRef = useRef(0);

  const proposeMutation = useMutation({
    mutationFn: async (id: string) => {
      const epoch = proposeEpochRef.current;
      try {
        const data = await proposeCities(id);
        return { data, epoch, id, ok: true as const };
      } catch (err) {
        return { err, epoch, id, ok: false as const };
      }
    },
    onSuccess: (result) => {
      if (result.epoch !== proposeEpochRef.current) return;
      if (tripId !== result.id) return;
      if (!result.ok) {
        const message =
          result.err instanceof Error
            ? result.err.message
            : "Failed to propose cities";
        onActionError(message);
        return;
      }
      onActionError(null);
      onApplied((prev) => {
        if (prev.trip?.trip_id && prev.trip.trip_id !== result.id) return prev;
        return applyTripBundle({
          trip: result.data.trip,
          route: result.data.route,
          days: prev.days,
        });
      });
      invalidateTrip(queryClient, result.id);
    },
  });

  const confirmMutation = useMutation({
    mutationFn: ({ id, route }: { id: string; route: Route }) =>
      confirmCities(id, route),
    onSuccess: (data, { id }) => {
      if (tripId !== id) return;
      onActionError(null);
      onApplied((prev) => {
        if (prev.trip?.trip_id && prev.trip.trip_id !== id) return prev;
        return applyTripBundle({
          trip: data.trip,
          route: data.route,
          days: prev.days,
        });
      });
      invalidateTrip(queryClient, id);
    },
    onError: (err: Error, { id }) => {
      if (tripId !== id) return;
      onActionError(err.message);
    },
  });

  const planDayMutation = useMutation({
    mutationFn: async ({ id, resumeDayIndex }: PlanDayVars) => {
      const epoch = planEpochRef.current;
      try {
        const data = await executePlanDayRequest(id, {
          resumeDayIndex,
          onAsyncStarted: (trip) => {
            if (planEpochRef.current !== epoch) return;
            if (tripId !== id) return;
            onApplied((prev) => {
              if (prev.trip?.trip_id && prev.trip.trip_id !== id) return prev;
              return { ...prev, trip };
            });
          },
        });
        return { data, epoch, id, ok: true as const };
      } catch (err) {
        return { err, epoch, id, ok: false as const };
      }
    },
    onSuccess: (result) => {
      if (planEpochRef.current !== result.epoch) return;
      if (tripId !== result.id) return;
      if (!result.ok) {
        const message =
          result.err instanceof Error
            ? result.err.message
            : "Failed to plan next day";
        onActionError(message);
        return;
      }
      onActionError(null);
      const day = result.data.day;
      const id = result.id;
      onApplied((prev) => {
        if (prev.trip?.trip_id && prev.trip.trip_id !== id) return prev;
        const nextDays = [
          ...prev.days.filter((d) => d.day_index !== day.day_index),
          day,
        ].sort((a, b) => a.day_index - b.day_index);
        return {
          ...prev,
          trip: result.data.trip,
          days: nextDays,
        };
      });
      invalidateTrip(queryClient, id);
    },
  });

  const suggestPlaceMutation = useMutation({
    mutationFn: ({ id, dayIndex }: { id: string; dayIndex: number }) =>
      suggestPlace(id, dayIndex),
    onSuccess: (data, { id }) => {
      if (tripId !== id) return;
      onActionError(null);
      const day = data.day;
      onApplied((prev) => {
        if (prev.trip?.trip_id && prev.trip.trip_id !== id) return prev;
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
    onError: (err: Error, { id }) => {
      if (tripId !== id) return;
      onActionError(err.message);
    },
  });

  const removePlaceMutation = useMutation({
    mutationFn: ({
      id,
      dayIndex,
      placeIndex,
    }: {
      id: string;
      dayIndex: number;
      placeIndex: number;
    }) => removePlace(id, dayIndex, placeIndex),
    onSuccess: (data, { id }) => {
      if (tripId !== id) return;
      onActionError(null);
      const day = data.day;
      onApplied((prev) => {
        if (prev.trip?.trip_id && prev.trip.trip_id !== id) return prev;
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
    onError: (err: Error, { id }) => {
      if (tripId !== id) return;
      onActionError(err.message);
    },
  });

  const deleteDayMutation = useMutation({
    mutationFn: ({ id, dayIndex }: { id: string; dayIndex: number }) =>
      deleteDay(id, dayIndex),
    onSuccess: (data, { id }) => {
      if (tripId !== id) return;
      onActionError(null);
      onApplied((prev) => {
        if (prev.trip?.trip_id && prev.trip.trip_id !== id) return prev;
        return {
          ...prev,
          trip: data.trip,
          days: data.days.map((d) => ({
            ...d,
            places: d.places.map((p) => ({ ...p })),
          })),
        };
      });
      invalidateTrip(queryClient, id);
    },
    onError: (err: Error, { id }) => {
      if (tripId !== id) return;
      onActionError(err.message);
    },
  });

  async function hydrateFromApi(id: string) {
    const epoch = ++hydrateEpochRef.current;
    const bundle = await getTrip(id);
    if (hydrateEpochRef.current !== epoch) {
      return { bundle, applied: false as const };
    }
    onApplied(applyTripBundle(bundle));
    const resume = pendingPlanningDayIndex(bundle.trip, bundle.days);
    if (resume != null && !planDayMutation.isPending) {
      planDayMutation.mutate({ id, resumeDayIndex: resume });
    }
    return { bundle, applied: true as const };
  }

  function runPropose(idOverride?: string) {
    const id = idOverride ?? tripId;
    if (!id) return;
    proposeEpochRef.current += 1;
    proposeMutation.mutate(id);
  }

  function cancelPropose() {
    proposeEpochRef.current += 1;
    planEpochRef.current += 1;
    hydrateEpochRef.current += 1;
    proposeMutation.reset();
    confirmMutation.reset();
    planDayMutation.reset();
    suggestPlaceMutation.reset();
    removePlaceMutation.reset();
    deleteDayMutation.reset();
  }

  function runConfirm(route: Route) {
    if (!tripId) return;
    confirmMutation.mutate({ id: tripId, route });
  }

  function runPlanNextDay(idOverride?: string) {
    const id = idOverride ?? tripId;
    if (!id) return;
    planDayMutation.mutate({ id });
  }

  function runSuggestPlace(dayIndex: number) {
    if (!tripId) return;
    suggestPlaceMutation.mutate({ id: tripId, dayIndex });
  }

  function runRemovePlace(dayIndex: number, placeIndex: number) {
    if (!tripId) return;
    removePlaceMutation.mutate({ id: tripId, dayIndex, placeIndex });
  }

  function runDeleteDay(dayIndex: number) {
    if (!tripId) return;
    deleteDayMutation.mutate({ id: tripId, dayIndex });
  }

  return {
    proposeMutation,
    confirmMutation,
    planDayMutation,
    suggestPlaceMutation,
    removePlaceMutation,
    deleteDayMutation,
    hydrateFromApi,
    runPropose,
    cancelPropose,
    runConfirm,
    runPlanNextDay,
    runSuggestPlace,
    runRemovePlace,
    runDeleteDay,
  };
}
