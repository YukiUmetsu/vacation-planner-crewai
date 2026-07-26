import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import {
  confirmCities,
  deleteDay,
  getTrip,
  proposeCities,
  removePlace,
  reorderPlace,
  suggestCity,
  suggestPlace,
  type CitySuggestion,
} from "../api/trips";
import type { CityStop, DayPlan, Route, Trip, TripBundle } from "../types/trip";
import { useRef, type SetStateAction } from "react";
import { executePlanDayRequest } from "./executePlanDayRequest";
import {
  pollUntilProposeReady,
  pollUntilSuggestCityReady,
  pollUntilSuggestPlaceReady,
} from "./pollCrewJob";
import { trackProductEvent } from "./productEvents";

/** Stable fingerprint of a city route for "accepted without edit" metrics. */
export function routeAcceptanceFingerprint(route: Route): string {
  const cities = (route.cities ?? []).map((c) => ({
    city: c.city,
    nights: c.nights,
    arrival_day_index: c.arrival_day_index,
    departure_day_index: c.departure_day_index,
  }));
  return JSON.stringify({
    destination_type: route.destination_type,
    total_nights: route.total_nights,
    cities,
  });
}

/**
 * Baseline fingerprint for an unconfirmed proposal (in-session or hydrated).
 * Confirmed routes are not a proposal baseline.
 */
export function acceptanceBaselineFromRoute(
  route: Route | null | undefined,
): string | null {
  if (!route) return null;
  if (route.status === "confirmed") return null;
  return routeAcceptanceFingerprint(route);
}

/** Epoch ms when the current proposal became available (prefer route.updated_at). */
export function proposalShownAtMs(
  route: Route | null | undefined,
  fallbackMs: number = Date.now(),
): number | null {
  if (acceptanceBaselineFromRoute(route) == null) return null;
  const raw = route?.updated_at?.trim();
  if (raw) {
    const parsed = Date.parse(raw);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallbackMs;
}

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
  /** Fingerprint of last successful propose — used for acceptance-without-edit. */
  const lastProposedFingerprintRef = useRef<string | null>(null);
  /** ms timestamp when proposal baseline was set (propose or hydrate). */
  const proposalShownAtRef = useRef<number | null>(null);

  const proposeMutation = useMutation({
    mutationFn: async (id: string) => {
      const epoch = proposeEpochRef.current;
      try {
        const started = await proposeCities(id);
        if (started.status === 202) {
          if (tripId === id && proposeEpochRef.current === epoch) {
            onApplied((prev) => {
              if (prev.trip?.trip_id && prev.trip.trip_id !== id) return prev;
              return { ...prev, trip: started.trip };
            });
          }
          const data = await pollUntilProposeReady(id);
          return { data, epoch, id, ok: true as const };
        }
        return {
          data: { trip: started.trip, route: started.route },
          epoch,
          id,
          ok: true as const,
        };
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
      lastProposedFingerprintRef.current = acceptanceBaselineFromRoute(
        result.data.route,
      );
      proposalShownAtRef.current = proposalShownAtMs(result.data.route);
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
    onSuccess: (data, { id, route }) => {
      if (tripId !== id) return;
      onActionError(null);
      // Ignore in-flight plan writes; days may have been remapped onto new indexes.
      planEpochRef.current += 1;
      const fingerprint = routeAcceptanceFingerprint(route);
      const withoutEdit =
        lastProposedFingerprintRef.current != null &&
        lastProposedFingerprintRef.current === fingerprint;
      const shownAt = proposalShownAtRef.current;
      void trackProductEvent("proposal_accepted", {
        tripId: id,
        payload: { source: "confirm_cities" },
      });
      if (withoutEdit) {
        void trackProductEvent("proposal_accepted_without_edit", {
          tripId: id,
          payload: { source: "confirm_cities" },
        });
      } else if (lastProposedFingerprintRef.current != null) {
        void trackProductEvent("manual_edit", {
          tripId: id,
          payload: { source: "confirm_cities" },
        });
      }
      if (shownAt != null) {
        void trackProductEvent("time_to_accept", {
          tripId: id,
          payload: {
            source: "confirm_cities",
            ms: Math.max(0, Date.now() - shownAt),
          },
        });
      }
      lastProposedFingerprintRef.current = null;
      proposalShownAtRef.current = null;
      onApplied((prev) => {
        if (prev.trip?.trip_id && prev.trip.trip_id !== id) return prev;
        return applyTripBundle({
          trip: data.trip,
          route: data.route,
          days: data.days ?? [],
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
        // Sync trip from server so a terminal failure clears stale
        // planning_day_index (set in onAsyncStarted) and status=failed sticks.
        void getTrip(result.id)
          .then((bundle) => {
            if (planEpochRef.current !== result.epoch) return;
            if (tripId !== result.id) return;
            onApplied((prev) => {
              if (prev.trip?.trip_id && prev.trip.trip_id !== result.id) {
                return prev;
              }
              return {
                ...prev,
                trip: bundle.trip,
                days: bundle.days.length
                  ? bundle.days.map((d) => ({
                      ...d,
                      places: d.places.map((p) => ({ ...p })),
                    }))
                  : prev.days,
              };
            });
          })
          .catch(() => {
            /* keep local error message; hydrate can recover later */
          });
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
    mutationFn: async ({
      id,
      dayIndex,
      hint,
    }: {
      id: string;
      dayIndex: number;
      hint?: string;
    }) => {
      const started = await suggestPlace(id, dayIndex, { hint });
      if (started.status === 202) {
        if (tripId === id) {
          onApplied((prev) => {
            if (prev.trip?.trip_id && prev.trip.trip_id !== id) return prev;
            return { ...prev, trip: started.trip };
          });
        }
        return pollUntilSuggestPlaceReady(
          id,
          started.day_index,
          started.baseline_place_count,
        );
      }
      return {
        place: started.place,
        day: started.day,
        trip: started.trip,
      };
    },
    onSuccess: (data, { id }) => {
      if (tripId !== id) return;
      onActionError(null);
      const day = data.day;
      void trackProductEvent("suggestion_accepted", {
        tripId: id,
        dayIndex: day.day_index,
      });
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
    onSuccess: (data, { id, dayIndex }) => {
      if (tripId !== id) return;
      onActionError(null);
      void trackProductEvent("place_deleted", { tripId: id, dayIndex });
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

  const reorderPlaceMutation = useMutation({
    mutationFn: ({
      id,
      dayIndex,
      fromIndex,
      toIndex,
    }: {
      id: string;
      dayIndex: number;
      fromIndex: number;
      toIndex: number;
      previousDays?: DayPlan[];
    }) => reorderPlace(id, dayIndex, fromIndex, toIndex),
    onSuccess: (data, { id, dayIndex, fromIndex, toIndex }) => {
      if (tripId !== id) return;
      onActionError(null);
      void trackProductEvent("place_reordered", {
        tripId: id,
        dayIndex,
        payload: { from_index: fromIndex, to_index: toIndex },
      });
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
    onError: (err: Error, { id, previousDays }) => {
      if (tripId !== id) return;
      onActionError(err.message);
      if (previousDays) {
        onApplied((prev) => {
          if (prev.trip?.trip_id && prev.trip.trip_id !== id) return prev;
          return { ...prev, days: previousDays };
        });
      }
      invalidateTrip(queryClient, id);
    },
  });

  const suggestCityMutation = useMutation({
    mutationFn: async ({
      id,
      cities,
      hint,
      count,
    }: {
      id: string;
      cities?: CityStop[];
      hint?: string;
      count?: number;
    }) => {
      const started = await suggestCity(id, {
        cities: cities?.map((c) => ({
          city: c.city,
          country: c.country,
          nights: c.nights,
          reason: c.reason,
        })),
        hint,
        count,
      });
      if (started.status === 202) {
        if (tripId === id) {
          onApplied((prev) => {
            if (prev.trip?.trip_id && prev.trip.trip_id !== id) return prev;
            return { ...prev, trip: started.trip };
          });
        }
        return pollUntilSuggestCityReady(id);
      }
      return {
        candidates: started.candidates,
        trip: started.trip,
      };
    },
    onSuccess: (data, { id }) => {
      if (tripId !== id) return;
      onActionError(null);
      onApplied((prev) => {
        if (prev.trip?.trip_id && prev.trip.trip_id !== id) return prev;
        return {
          ...prev,
          trip: {
            ...data.trip,
            suggest_city_candidates: data.candidates,
          },
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
    onSuccess: (data, { id, dayIndex }) => {
      if (tripId !== id) return;
      onActionError(null);
      void trackProductEvent("plan_regenerated", {
        tripId: id,
        dayIndex,
        payload: { action: "delete_day" },
      });
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
    lastProposedFingerprintRef.current = acceptanceBaselineFromRoute(
      bundle.route,
    );
    proposalShownAtRef.current = proposalShownAtMs(bundle.route);
    const resume = pendingPlanningDayIndex(bundle.trip, bundle.days);
    if (resume != null && !planDayMutation.isPending) {
      planDayMutation.mutate({ id, resumeDayIndex: resume });
    }
    const job = bundle.trip.crew_job_kind;
    if (job === "propose_cities" && !proposeMutation.isPending) {
      void pollUntilProposeReady(id).then(
        (data) => {
          if (hydrateEpochRef.current !== epoch) return;
          if (tripId !== id) return;
          lastProposedFingerprintRef.current = acceptanceBaselineFromRoute(
            data.route,
          );
          proposalShownAtRef.current = proposalShownAtMs(data.route);
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
        (err: Error) => {
          if (tripId !== id) return;
          onActionError(err.message);
        },
      );
    } else if (job === "suggest_place" && !suggestPlaceMutation.isPending) {
      const dayIndex = Number(bundle.trip.crew_job_day_index);
      const baseline = Number(bundle.trip.crew_job_baseline_place_count ?? 0);
      if (Number.isFinite(dayIndex) && dayIndex >= 1) {
        void pollUntilSuggestPlaceReady(id, dayIndex, baseline).then(
          (data) => {
            if (hydrateEpochRef.current !== epoch) return;
            if (tripId !== id) return;
            onApplied((prev) => {
              if (prev.trip?.trip_id && prev.trip.trip_id !== id) return prev;
              const nextDays = [
                ...prev.days.filter((d) => d.day_index !== data.day.day_index),
                data.day,
              ].sort((a, b) => a.day_index - b.day_index);
              return { ...prev, trip: data.trip, days: nextDays };
            });
            invalidateTrip(queryClient, id);
          },
          (err: Error) => {
            if (tripId !== id) return;
            onActionError(err.message);
          },
        );
      }
    } else if (
      job === "suggest_city" &&
      !suggestCityMutation.isPending &&
      !(
        Array.isArray(bundle.trip.suggest_city_candidates) &&
        bundle.trip.suggest_city_candidates.length > 0
      )
    ) {
      void pollUntilSuggestCityReady(id).then(
        (data) => {
          if (hydrateEpochRef.current !== epoch) return;
          if (tripId !== id) return;
          onApplied((prev) => {
            if (prev.trip?.trip_id && prev.trip.trip_id !== id) return prev;
            return {
              ...prev,
              trip: {
                ...data.trip,
                suggest_city_candidates: data.candidates,
              },
            };
          });
          invalidateTrip(queryClient, id);
        },
        (err: Error) => {
          if (tripId !== id) return;
          onActionError(err.message);
        },
      );
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
    lastProposedFingerprintRef.current = null;
    proposalShownAtRef.current = null;
    proposeMutation.reset();
    confirmMutation.reset();
    planDayMutation.reset();
    suggestPlaceMutation.reset();
    removePlaceMutation.reset();
    reorderPlaceMutation.reset();
    suggestCityMutation.reset();
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

  function runSuggestPlace(dayIndex: number, hint?: string) {
    if (!tripId) return;
    suggestPlaceMutation.mutate({ id: tripId, dayIndex, hint });
  }

  function runRemovePlace(dayIndex: number, placeIndex: number) {
    if (!tripId) return;
    removePlaceMutation.mutate({ id: tripId, dayIndex, placeIndex });
  }

  function runReorderPlace(
    dayIndex: number,
    fromIndex: number,
    toIndex: number,
    previousDays?: DayPlan[],
  ) {
    if (!tripId) return;
    reorderPlaceMutation.mutate({
      id: tripId,
      dayIndex,
      fromIndex,
      toIndex,
      previousDays,
    });
  }

  async function runSuggestCity(input?: {
    cities?: CityStop[];
    hint?: string;
    count?: number;
  }): Promise<CitySuggestion[]> {
    if (!tripId) return [];
    const data = await suggestCityMutation.mutateAsync({
      id: tripId,
      cities: input?.cities,
      hint: input?.hint,
      count: input?.count,
    });
    return data.candidates ?? [];
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
    reorderPlaceMutation,
    suggestCityMutation,
    deleteDayMutation,
    hydrateFromApi,
    runPropose,
    cancelPropose,
    runConfirm,
    runPlanNextDay,
    runSuggestPlace,
    runRemovePlace,
    runReorderPlace,
    runSuggestCity,
    runDeleteDay,
  };
}
