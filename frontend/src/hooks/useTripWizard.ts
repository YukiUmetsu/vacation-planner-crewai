import { useEffect, useMemo, useRef, useState, type SetStateAction } from "react";
import { placeFromDraft, type PlaceDraft } from "../components/days/AddPlaceForm";
import type { UserProfile } from "../components/profile/ProfilePage";
import type { WizardStep } from "../components/WizardLayout";
import { getProfile, putProfile, profileFromApi } from "../api/profile";
import { listTrips, deleteTrip } from "../api/trips";
import {
  DEMO_CITIES,
  DEMO_DAYS,
  DEMO_TRIP_BUNDLE,
  demoFeasibilityMessage,
} from "../demo/tripDemo";
import { DEMO_PLACE_SUGGESTIONS } from "../demo/placeDetails";
import {
  appendPlaceToDays,
  removeDayFromDays,
  removePlaceFromDays,
} from "../lib/dayPlaces";
import {
  addCityStop,
  overnightCityForDay,
  removeCityAtIndex,
  removeCityByClientId,
  routeWindowIssue,
  setCityNights,
} from "../lib/cityRoute";
import {
  buildConfirmRoute,
  emptyLiveTripState,
  pendingPlanningDayIndex,
  useLiveTripActions,
  type LiveTripState,
} from "../lib/liveTrip";
import { loadProfile, saveProfile } from "../lib/profileStorage";
import { pickLatestIncompleteTrip, shouldAutoStartDayPlanning } from "../lib/tripStatus";
import type { CityStop, DayPlan, Route, Trip } from "../types/trip";

export type TripScreen = "trip" | "profile";

function cloneDemoCities(): CityStop[] {
  return DEMO_CITIES.map((c) => ({ ...c }));
}

function cloneDemoDays(): DayPlan[] {
  return DEMO_DAYS.map((d) => ({
    ...d,
    places: d.places.map((p) => ({ ...p })),
  }));
}

/** Shared wizard state + handlers for demo and live trip flows. */
export function useTripWizard(demoMode: boolean) {
  const [screen, setScreen] = useState<TripScreen>("trip");
  const [step, setStep] = useState<WizardStep>("details");
  const [tripId, setTripId] = useState<string | null>(null);
  const [tripsList, setTripsList] = useState<Trip[]>([]);
  const [tripsLoading, setTripsLoading] = useState(false);
  /** True after the first listTrips attempt finishes (success or failure). */
  const [tripsReady, setTripsReady] = useState(false);
  const [deletingTripId, setDeletingTripId] = useState<string | null>(null);
  const [demoCities, setDemoCities] = useState<CityStop[]>(cloneDemoCities);
  const [demoDays, setDemoDays] = useState<DayPlan[]>(cloneDemoDays);
  const [live, setLive] = useState<LiveTripState>(emptyLiveTripState);
  const [actionError, setActionError] = useState<string | null>(null);
  const [hydrating, setHydrating] = useState(false);
  /** Skip auto-resume once the user explicitly starts a blank trip. */
  const skipAutoResumeRef = useRef(false);
  const autoResumeDoneRef = useRef(false);
  /** Avoid double plan-next-day when confirm + days-step effect both fire. */
  const autoPlanDaysKeyRef = useRef<string | null>(null);
  const [feasibilityMessage, setFeasibilityMessage] = useState<string | null>(
    null,
  );
  const [checkingCity, setCheckingCity] = useState<string | null>(null);
  const [lastAddedClientId, setLastAddedClientId] = useState<string | null>(
    null,
  );
  const [suggestPendingDay, setSuggestPendingDay] = useState<number | null>(
    null,
  );
  const [demoProposePending, setDemoProposePending] = useState(false);
  const [profile, setProfile] = useState<UserProfile>(() => loadProfile());
  const profileSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingProfileRef = useRef<UserProfile | null>(null);
  const demoProposeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (demoMode) return;
    let cancelled = false;
    void getProfile()
      .then(({ profile: apiProfile }) => {
        if (cancelled) return;
        // Defaults from GET (persisted=false) must not wipe richer localStorage.
        if (apiProfile.persisted === false) return;
        const next = profileFromApi(apiProfile);
        setProfile(next);
        saveProfile(next);
      })
      .catch(() => {
        // Offline / AUTH_MODE failures keep local.
      });
    return () => {
      cancelled = true;
    };
  }, [demoMode]);

  async function refreshTripsList(): Promise<Trip[]> {
    const { trips } = await listTrips();
    setTripsList(trips);
    return trips;
  }

  useEffect(() => {
    return () => {
      if (profileSaveTimer.current) clearTimeout(profileSaveTimer.current);
      if (demoProposeTimer.current) clearTimeout(demoProposeTimer.current);
      const pending = pendingProfileRef.current;
      pendingProfileRef.current = null;
      if (!demoMode && pending) {
        void putProfile(pending).catch(() => {
          // Best-effort flush on unmount; localStorage already has the latest.
        });
      }
    };
  }, [demoMode]);

  const cities = demoMode ? demoCities : live.cities;
  const days = demoMode ? demoDays : live.days;

  const setCities = demoMode
    ? setDemoCities
    : (updater: SetStateAction<CityStop[]>) => {
        setLive((prev) => ({
          ...prev,
          cities:
            typeof updater === "function" ? updater(prev.cities) : updater,
        }));
      };

  const setDays = demoMode
    ? setDemoDays
    : (updater: SetStateAction<DayPlan[]>) => {
        setLive((prev) => ({
          ...prev,
          days: typeof updater === "function" ? updater(prev.days) : updater,
        }));
      };

  const liveActions = useLiveTripActions({
    tripId,
    onApplied: setLive,
    onActionError: setActionError,
  });

  // Live mode: fetch the user's trips for the details switcher.
  useEffect(() => {
    if (demoMode) return;
    let cancelled = false;
    setTripsLoading(true);
    void refreshTripsList()
      .catch(() => {
        // List failures leave the blank create form; user can still create.
      })
      .finally(() => {
        if (cancelled) return;
        setTripsLoading(false);
        setTripsReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [demoMode]);

  // Resume the newest incomplete trip once the list is ready (details stays open).
  useEffect(() => {
    if (demoMode || !tripsReady || tripsLoading || tripId) return;
    if (skipAutoResumeRef.current || autoResumeDoneRef.current) return;

    const latest = pickLatestIncompleteTrip(tripsList);
    if (!latest) {
      autoResumeDoneRef.current = true;
      return;
    }

    let cancelled = false;
    setHydrating(true);
    void liveActions
      .hydrateFromApi(latest.trip_id)
      .then((result) => {
        if (cancelled || !result.applied) return;
        autoResumeDoneRef.current = true;
        setTripId(latest.trip_id);
        setStep("details");
      })
      .catch((err) => {
        if (cancelled) return;
        autoResumeDoneRef.current = true;
        setActionError(
          err instanceof Error ? err.message : "Failed to load saved trip",
        );
      })
      .finally(() => {
        if (!cancelled) setHydrating(false);
      });

    return () => {
      cancelled = true;
      setHydrating(false);
    };
    // liveActions changes often; resume only when list / tripId settle.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional resume deps
  }, [demoMode, tripsReady, tripsLoading, tripsList, tripId]);

  // Days step: if there are no day plans yet, start planning automatically
  // (fresh confirm or reopening an old trip that never planned day 1).
  useEffect(() => {
    if (demoMode || step !== "days" || hydrating || !tripId) return;
    if (liveActions.planDayMutation.isPending) return;
    if (!live.trip) return;
    if (
      !shouldAutoStartDayPlanning({
        trip: live.trip,
        route: live.routeMeta,
        days: live.days,
      })
    ) {
      return;
    }
    // In-flight worker resume is handled inside hydrateFromApi.
    if (pendingPlanningDayIndex(live.trip, live.days) != null) return;

    const key = `${tripId}:empty-days`;
    if (autoPlanDaysKeyRef.current === key) return;
    autoPlanDaysKeyRef.current = key;
    liveActions.runPlanNextDay(tripId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- kick once per empty days visit
  }, [
    demoMode,
    step,
    hydrating,
    tripId,
    live.trip,
    live.days,
    live.routeMeta,
    liveActions.planDayMutation.isPending,
  ]);

  const demoTrip = useMemo(() => ({ ...DEMO_TRIP_BUNDLE.trip }), []);
  const dayCount = demoMode
    ? demoTrip.day_count
    : (live.trip?.day_count ?? 0);

  const demoRoute = useMemo(
    (): Route => ({
      ...DEMO_TRIP_BUNDLE.route!,
      cities: demoCities,
      total_nights: demoCities.reduce((sum, c) => sum + c.nights, 0),
      status: "confirmed",
    }),
    [demoCities],
  );

  function updateProfile(next: UserProfile) {
    setProfile(next);
    saveProfile(next);
    if (demoMode) return;
    pendingProfileRef.current = next;
    if (profileSaveTimer.current) clearTimeout(profileSaveTimer.current);
    profileSaveTimer.current = setTimeout(() => {
      const toSave = pendingProfileRef.current;
      pendingProfileRef.current = null;
      if (!toSave) return;
      void putProfile(toSave).catch(() => {
        // Local cache already updated; retry on next edit / reload.
      });
    }, 600);
  }

  function handleAddCity(city: string, reason: string) {
    const clientId =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `city-${Date.now()}`;
    const updated = addCityStop(
      cities,
      {
        city,
        country: demoMode ? "Japan" : undefined,
        nights: 1,
        reason: reason || (demoMode ? "Added in demo" : "Added by traveler"),
        client_id: clientId,
      },
      dayCount || undefined,
    );
    setCities(updated);
    setLastAddedClientId(clientId);
    setCheckingCity(city);
    setFeasibilityMessage(null);

    if (!demoMode) {
      setCheckingCity(null);
      return;
    }

    window.setTimeout(() => {
      setCheckingCity(null);
      setFeasibilityMessage(demoFeasibilityMessage(updated));
    }, 600);
  }

  async function handleCreatedTrip(id: string) {
    // Defer setTripId until hydrate finishes so CreateTripForm does not remount
    // into edit mode mid-create (which would clear isPending / allow double-submit).
    skipAutoResumeRef.current = false;
    setLive(emptyLiveTripState());
    setActionError(null);
    setHydrating(true);
    try {
      const { bundle, applied } = await liveActions.hydrateFromApi(id);
      if (!applied) return;
      setTripId(id);
      void refreshTripsList().catch(() => {});
      // City destinations already have a synthetic confirmed route.
      if (bundle.trip.destination_type !== "city") {
        liveActions.runPropose(id);
      }
      setStep("cities");
    } catch (err) {
      setTripId(id);
      void refreshTripsList().catch(() => {});
      setActionError(
        err instanceof Error ? err.message : "Failed to start city proposal",
      );
    } finally {
      setHydrating(false);
    }
  }

  async function handleUpdatedTrip(id: string) {
    setActionError(null);
    setHydrating(true);
    try {
      const { bundle, applied } = await liveActions.hydrateFromApi(id);
      if (!applied) return;
      void refreshTripsList().catch(() => {});
      // City destinations skip propose (synthetic route already on the trip).
      if (bundle.trip.destination_type === "city") {
        setStep("cities");
        return;
      }
      liveActions.runPropose(id);
      setStep("cities");
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to update trip",
      );
    } finally {
      setHydrating(false);
    }
  }

  async function selectTrip(id: string) {
    if (id === tripId) {
      setStep("details");
      return;
    }
    skipAutoResumeRef.current = false;
    liveActions.cancelPropose();
    setActionError(null);
    setHydrating(true);
    try {
      const { applied } = await liveActions.hydrateFromApi(id);
      if (!applied) return;
      setTripId(id);
      setStep("details");
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to load trip",
      );
    } finally {
      setHydrating(false);
    }
  }

  function startNewTrip() {
    skipAutoResumeRef.current = true;
    liveActions.cancelPropose();
    setTripId(null);
    setLive(emptyLiveTripState());
    setActionError(null);
    setStep("details");
  }

  async function removeTrip(id: string) {
    setActionError(null);
    setDeletingTripId(id);
    try {
      await deleteTrip(id);
      const remaining = tripsList.filter((t) => t.trip_id !== id);
      setTripsList(remaining);

      if (tripId === id) {
        liveActions.cancelPropose();
        const next = pickLatestIncompleteTrip(remaining);
        if (next) {
          setHydrating(true);
          try {
            const { applied } = await liveActions.hydrateFromApi(next.trip_id);
            if (!applied) return;
            setTripId(next.trip_id);
          } catch (err) {
            setTripId(null);
            setLive(emptyLiveTripState());
            skipAutoResumeRef.current = true;
            setActionError(
              err instanceof Error ? err.message : "Failed to load next trip",
            );
          } finally {
            setHydrating(false);
          }
        } else {
          skipAutoResumeRef.current = true;
          setTripId(null);
          setLive(emptyLiveTripState());
        }
        setStep("details");
      }
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to remove trip",
      );
    } finally {
      setDeletingTripId(null);
    }
  }

  function goToDetails() {
    liveActions.cancelPropose();
    setActionError(null);
    setStep("details");
  }

  async function goToCities() {
    setActionError(null);
    if (demoMode) {
      setStep("cities");
      return;
    }
    if (!tripId) {
      setActionError("Create a trip before reviewing cities.");
      return;
    }
    setHydrating(true);
    try {
      const { bundle, applied } = await liveActions.hydrateFromApi(tripId);
      if (!applied) return;
      setStep("cities");
      const hasCities = (bundle.route?.cities?.length ?? 0) > 0;
      if (!hasCities && !liveActions.proposeMutation.isPending) {
        liveActions.runPropose(tripId);
      }
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to load trip",
      );
    } finally {
      setHydrating(false);
    }
  }

  async function goToDays() {
    setActionError(null);
    if (demoMode) {
      setStep("days");
      if (demoDays.length === 0) handlePlanNextDay();
      return;
    }
    if (!tripId) {
      setActionError("Create a trip before planning days.");
      return;
    }
    setHydrating(true);
    try {
      const { applied } = await liveActions.hydrateFromApi(tripId);
      if (!applied) return;
      // Reset so the days-step effect can kick plan-next-day for empty itineraries.
      autoPlanDaysKeyRef.current = null;
      setStep("days");
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to load trip",
      );
    } finally {
      setHydrating(false);
    }
  }

  function handlePlanNextDay() {
    if (!demoMode) {
      liveActions.runPlanNextDay();
      return;
    }
    const nextIndex = days.length + 1;
    if (nextIndex > dayCount) return;
    const overnight =
      overnightCityForDay(cities, nextIndex) ??
      cities[cities.length - 1]?.city ??
      "Tokyo";

    setDemoDays((prev) => [
      ...prev,
      {
        day_index: nextIndex,
        date: `2026-08-${String(nextIndex).padStart(2, "0")}`,
        theme: `Demo day ${nextIndex}`,
        overnight_city: overnight,
        places: [
          {
            name: `Sample place ${nextIndex}A`,
            place_key: `demo-${nextIndex}-a`,
          },
          {
            name: `Sample place ${nextIndex}B`,
            place_key: `demo-${nextIndex}-b`,
          },
        ],
      },
    ]);
  }

  function handleSuggestPlace(dayIndex: number) {
    if (!demoMode) {
      liveActions.runSuggestPlace(dayIndex);
      return;
    }
    const day = days.find((d) => d.day_index === dayIndex);
    if (!day) return;
    setSuggestPendingDay(dayIndex);
    window.setTimeout(() => {
      const pool =
        DEMO_PLACE_SUGGESTIONS[day.overnight_city] ??
        DEMO_PLACE_SUGGESTIONS.Tokyo;
      const existing = new Set(day.places.map((p) => p.place_key));
      const pick =
        pool.find((p) => !existing.has(p.place_key)) ??
        pool[Math.floor(Math.random() * pool.length)];
      setDays((prev) => appendPlaceToDays(prev, dayIndex, pick));
      setSuggestPendingDay(null);
    }, 500);
  }

  function handlePropose() {
    if (demoMode) {
      if (demoProposeTimer.current) clearTimeout(demoProposeTimer.current);
      setDemoProposePending(true);
      setLastAddedClientId(null);
      setFeasibilityMessage(null);
      // Keep the loading canvas up long enough to see a quote/question rotate.
      demoProposeTimer.current = setTimeout(() => {
        setDemoCities(cloneDemoCities());
        setDemoProposePending(false);
        demoProposeTimer.current = null;
      }, 11_000);
      return;
    }
    liveActions.runPropose();
  }

  async function handleConfirm() {
    if (demoMode) {
      setStep("days");
      // Demo already ships with days; only plan if the list is empty.
      if (demoDays.length === 0) handlePlanNextDay();
      return;
    }
    if (!tripId) return;
    const issue = routeWindowIssue(live.cities, dayCount || null);
    if (issue) {
      setActionError(issue);
      return;
    }
    const route = buildConfirmRoute(live, live.cities);
    try {
      await liveActions.confirmMutation.mutateAsync({ id: tripId, route });
      // Let the days-step effect start plan-next-day when days are still empty.
      autoPlanDaysKeyRef.current = null;
      setStep("days");
    } catch {
      // error surfaced via onActionError
    }
  }

  function handleNightsChange(index: number, nights: number) {
    setCities((prev) => setCityNights(prev, index, nights, dayCount || undefined));
  }

  function handleRemoveCity(index: number) {
    const removed = cities[index];
    setCities((prev) => removeCityAtIndex(prev, index, dayCount || undefined));
    if (removed?.client_id && removed.client_id === lastAddedClientId) {
      setLastAddedClientId(null);
      setFeasibilityMessage(null);
    }
  }

  function handleKeepFeasibility() {
    setFeasibilityMessage(null);
  }

  function handleUndoFeasibility() {
    if (!lastAddedClientId) {
      setFeasibilityMessage(null);
      return;
    }
    setCities((prev) =>
      removeCityByClientId(prev, lastAddedClientId, dayCount || undefined),
    );
    setLastAddedClientId(null);
    setFeasibilityMessage(null);
  }

  function handleAddPlace(dayIndex: number, draft: PlaceDraft) {
    setDays((prev) => {
      const day = prev.find((d) => d.day_index === dayIndex);
      if (!day) return prev;
      const place = placeFromDraft(
        draft,
        day.places.length + 1,
        day.places.map((p) => p.place_key),
      );
      return appendPlaceToDays(prev, dayIndex, place);
    });
  }

  function handleRemovePlace(dayIndex: number, placeIndex: number) {
    if (!demoMode) {
      liveActions.runRemovePlace(dayIndex, placeIndex);
      return;
    }
    setDays((prev) => removePlaceFromDays(prev, dayIndex, placeIndex));
  }

  function handleRemoveDay(dayIndex: number) {
    if (!demoMode) {
      // Allow auto-plan to run again if this empties the itinerary.
      autoPlanDaysKeyRef.current = null;
      liveActions.runDeleteDay(dayIndex);
      return;
    }
    setDays((prev) => removeDayFromDays(prev, dayIndex));
  }

  const liveSuggestPending =
    !demoMode && liveActions.suggestPlaceMutation.isPending
      ? (liveActions.suggestPlaceMutation.variables?.dayIndex ?? null)
      : null;

  const destination = demoMode
    ? demoTrip.destination
    : (live.trip?.destination ?? "");

  return {
    demoMode,
    screen,
    setScreen,
    step,
    setStep,
    tripId,
    tripsList,
    tripsLoading,
    deletingTripId,
    profile,
    updateProfile,
    cities,
    days,
    dayCount,
    destination,
    demoTrip,
    demoRoute,
    demoDays,
    liveTrip: demoMode ? null : live.trip,
    liveRoute: demoMode ? null : live.routeMeta,
    hydrating,
    actionError,
    feasibilityMessage,
    checkingCity,
    suggestPendingDay: liveSuggestPending ?? suggestPendingDay,
    proposePending: demoProposePending || liveActions.proposeMutation.isPending,
    confirmPending: liveActions.confirmMutation.isPending || hydrating,
    planPending: liveActions.planDayMutation.isPending,
    handleCreatedTrip,
    handleUpdatedTrip,
    selectTrip,
    startNewTrip,
    removeTrip,
    goToDetails,
    goToCities,
    goToDays,
    handleAddCity,
    handlePropose,
    handleConfirm,
    handleKeepFeasibility,
    handleUndoFeasibility,
    handleNightsChange,
    handleRemoveCity,
    handlePlanNextDay,
    handleSuggestPlace,
    handleAddPlace,
    handleRemovePlace,
    handleRemoveDay,
  };
}

export type TripWizard = ReturnType<typeof useTripWizard>;
