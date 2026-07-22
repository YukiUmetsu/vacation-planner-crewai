import { useMemo, useState, type SetStateAction } from "react";
import { placeFromDraft, type PlaceDraft } from "../components/days/AddPlaceForm";
import type { UserProfile } from "../components/profile/ProfilePage";
import type { WizardStep } from "../components/WizardLayout";
import {
  DEMO_CITIES,
  DEMO_DAYS,
  DEMO_TRIP_BUNDLE,
  demoFeasibilityMessage,
} from "../demo/tripDemo";
import { DEMO_PLACE_SUGGESTIONS } from "../demo/placeDetails";
import {
  appendPlaceToDays,
  removePlaceFromDays,
} from "../lib/dayPlaces";
import {
  addCityStop,
  overnightCityForDay,
  removeCityByClientId,
  setCityNights,
} from "../lib/cityRoute";
import {
  buildConfirmRoute,
  emptyLiveTripState,
  useLiveTripActions,
  type LiveTripState,
} from "../lib/liveTrip";
import { loadProfile, saveProfile } from "../lib/profileStorage";
import type { CityStop, DayPlan, Route } from "../types/trip";

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
  const [demoCities, setDemoCities] = useState<CityStop[]>(cloneDemoCities);
  const [demoDays, setDemoDays] = useState<DayPlan[]>(cloneDemoDays);
  const [live, setLive] = useState<LiveTripState>(emptyLiveTripState);
  const [actionError, setActionError] = useState<string | null>(null);
  const [hydrating, setHydrating] = useState(false);
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
  const [profile, setProfile] = useState<UserProfile>(() => loadProfile());

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

  function handleCreatedTrip(id: string) {
    setTripId(id);
    setLive(emptyLiveTripState());
    setActionError(null);
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
      await liveActions.hydrateFromApi(tripId);
      setStep("cities");
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
      return;
    }
    if (!tripId) {
      setActionError("Create a trip before planning days.");
      return;
    }
    setHydrating(true);
    try {
      await liveActions.hydrateFromApi(tripId);
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
    if (!demoMode) return;
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
      setDemoCities(cloneDemoCities());
      setLastAddedClientId(null);
      setFeasibilityMessage(null);
      return;
    }
    liveActions.runPropose();
  }

  async function handleConfirm() {
    if (demoMode) {
      setStep("days");
      return;
    }
    if (!tripId) return;
    const route = buildConfirmRoute(live, live.cities);
    try {
      await liveActions.confirmMutation.mutateAsync({ id: tripId, route });
      setStep("days");
    } catch {
      // error surfaced via onActionError
    }
  }

  function handleNightsChange(index: number, nights: number) {
    setCities((prev) => setCityNights(prev, index, nights, dayCount || undefined));
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
    setDays((prev) => removePlaceFromDays(prev, dayIndex, placeIndex));
  }

  return {
    demoMode,
    screen,
    setScreen,
    step,
    setStep,
    tripId,
    profile,
    updateProfile,
    cities,
    days,
    dayCount,
    demoTrip,
    demoRoute,
    demoDays,
    hydrating,
    actionError,
    feasibilityMessage,
    checkingCity,
    suggestPendingDay,
    proposePending: liveActions.proposeMutation.isPending,
    confirmPending: liveActions.confirmMutation.isPending || hydrating,
    planPending: liveActions.planDayMutation.isPending,
    handleCreatedTrip,
    goToCities,
    goToDays,
    handleAddCity,
    handlePropose,
    handleConfirm,
    handleKeepFeasibility,
    handleUndoFeasibility,
    handleNightsChange,
    handlePlanNextDay,
    handleSuggestPlace,
    handleAddPlace,
    handleRemovePlace,
  };
}

export type TripWizard = ReturnType<typeof useTripWizard>;
