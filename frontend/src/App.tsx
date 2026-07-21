import { useMemo, useState } from "react";
import { CreateTripForm } from "./components/CreateTripForm";
import { TripGist, TripGistEmpty } from "./components/TripGist";
import { TripPanel } from "./components/TripPanel";
import { WizardLayout, type WizardStep } from "./components/WizardLayout";
import { CitiesPanel } from "./components/cities/CitiesPanel";
import { DaysPanel } from "./components/days/DaysPanel";
import { placeFromDraft } from "./components/days/AddPlaceForm";
import {
  ProfilePage,
  type UserProfile,
} from "./components/profile/ProfilePage";
import {
  DEMO_CITIES,
  DEMO_DAYS,
  DEMO_TRIP_BUNDLE,
  demoFeasibilityMessage,
} from "./demo/tripDemo";
import { DEMO_PROFILE } from "./demo/profileDemo";
import { DEMO_PLACE_SUGGESTIONS } from "./demo/placeDetails";
import {
  appendPlaceToDays,
  removePlaceFromDays,
} from "./lib/dayPlaces";
import {
  addCityStop,
  overnightCityForDay,
  removeCityByClientId,
  setCityNights,
} from "./lib/cityRoute";
import type { CityStop, DayPlan } from "./types/trip";

/**
 * DEMO MODE (default): browse UI with static Japan data + profile.
 * Set VITE_USE_DEMO_DATA=false (or pass demoMode={false}) for the live create flow.
 */
const DEFAULT_DEMO_MODE = import.meta.env.VITE_USE_DEMO_DATA !== "false";

type Screen = "trip" | "profile";

export type AppProps = {
  /** Override env default — used by tests for the live create path. */
  demoMode?: boolean;
};

export function App({ demoMode = DEFAULT_DEMO_MODE }: AppProps) {
  const [screen, setScreen] = useState<Screen>("trip");
  const [step, setStep] = useState<WizardStep>("details");
  const [tripId, setTripId] = useState<string | null>(null);
  const [cities, setCities] = useState<CityStop[]>(() =>
    DEMO_CITIES.map((c) => ({ ...c })),
  );
  const [days, setDays] = useState<DayPlan[]>(() =>
    DEMO_DAYS.map((d) => ({
      ...d,
      places: d.places.map((p) => ({ ...p })),
    })),
  );
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
  const [profile, setProfile] = useState<UserProfile>(() => ({
    ...DEMO_PROFILE,
    interests: [...DEMO_PROFILE.interests],
    visitedPlaces: DEMO_PROFILE.visitedPlaces.map((p) => ({ ...p })),
  }));

  const demoTrip = useMemo(() => ({ ...DEMO_TRIP_BUNDLE.trip }), []);

  const demoRoute = useMemo(
    () => ({
      ...DEMO_TRIP_BUNDLE.route!,
      cities,
      total_nights: cities.reduce((sum, c) => sum + c.nights, 0),
      status: "confirmed" as const,
    }),
    [cities],
  );

  function handleAddCity(city: string, reason: string) {
    const clientId =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `city-${Date.now()}`;
    const updated = addCityStop(cities, {
      city,
      country: "Japan",
      nights: 1,
      reason: reason || "Added in demo",
      client_id: clientId,
    });
    setCities(updated);
    setLastAddedClientId(clientId);
    setCheckingCity(city);
    setFeasibilityMessage(null);

    window.setTimeout(() => {
      setCheckingCity(null);
      setFeasibilityMessage(demoFeasibilityMessage(updated));
    }, 600);
  }

  function handleCreatedTrip(id: string) {
    setTripId(id);
  }

  function handlePlanNextDay() {
    const nextIndex = days.length + 1;
    if (nextIndex > demoTrip.day_count) return;
    const overnight =
      overnightCityForDay(cities, nextIndex) ??
      cities[cities.length - 1]?.city ??
      "Tokyo";

    setDays((prev) => [
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

  if (screen === "profile") {
    return (
      <div className="mx-auto min-h-dvh max-w-6xl px-4 py-8 sm:px-8 sm:py-10">
        <p className="mb-6 font-display text-3xl font-semibold text-ink">
          Vacation Planner
          {demoMode && (
            <span className="ml-3 align-middle rounded-full bg-teal-soft px-2.5 py-0.5 text-xs font-semibold text-teal-deep">
              Demo data
            </span>
          )}
        </p>
        <ProfilePage
          profile={profile}
          onChange={setProfile}
          onBack={() => setScreen("trip")}
        />
      </div>
    );
  }

  return (
    <WizardLayout
      step={step}
      onStepChange={demoMode ? setStep : undefined}
      demoBadge={demoMode}
      onOpenProfile={() => setScreen("profile")}
    >
      {step === "details" && (
        <div className="grid gap-8 lg:grid-cols-2 lg:gap-10">
          <section className="rounded-2xl border border-line/80 bg-surface/90 p-6 shadow-sm sm:p-8">
            {demoMode ? (
              <div className="space-y-4">
                <h2 className="font-display text-2xl font-semibold text-ink">
                  Demo trip loaded
                </h2>
                <p className="text-sm text-ink-muted">
                  Use the step rail, or open <strong>Profile</strong> for
                  preferences and places you’ve been. On Days:{" "}
                  <strong>Add place</strong> / <strong>Suggest a place</strong>.
                  Create-trip API is available when demo mode is off (
                  <code className="text-xs">VITE_USE_DEMO_DATA=false</code>).
                </p>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="rounded-lg bg-teal px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-deep"
                    onClick={() => setStep("cities")}
                  >
                    Go to cities
                  </button>
                  <button
                    type="button"
                    className="rounded-lg border border-teal bg-surface px-4 py-2.5 text-sm font-semibold text-teal hover:bg-teal-soft"
                    onClick={() => setStep("days")}
                  >
                    Go to days
                  </button>
                  <button
                    type="button"
                    className="rounded-lg border border-line bg-surface px-4 py-2.5 text-sm font-semibold text-ink hover:bg-sand"
                    onClick={() => setScreen("profile")}
                  >
                    Open profile
                  </button>
                </div>
              </div>
            ) : (
              <CreateTripForm onCreated={handleCreatedTrip} />
            )}
          </section>
          <section className="rounded-2xl border border-line/80 bg-surface/90 p-6 shadow-sm sm:p-8">
            {demoMode ? (
              <TripGist
                trip={demoTrip}
                route={demoRoute}
                days={days}
                onContinueToCities={() => setStep("cities")}
                onContinueToDays={() => setStep("days")}
              />
            ) : tripId ? (
              <TripPanel
                tripId={tripId}
                onContinueToCities={() => setStep("cities")}
                onContinueToDays={() => setStep("days")}
              />
            ) : (
              <TripGistEmpty />
            )}
          </section>
        </div>
      )}

      {step === "cities" && (
        <CitiesPanel
          cities={cities}
          checkingCity={checkingCity}
          feasibilityMessage={feasibilityMessage}
          onNightsChange={(index, nights) => {
            setCities((prev) => setCityNights(prev, index, nights));
          }}
          onAddCity={handleAddCity}
          onPropose={() => {
            setCities(DEMO_CITIES.map((c) => ({ ...c })));
            setLastAddedClientId(null);
            setFeasibilityMessage(null);
          }}
          onConfirm={() => setStep("days")}
          onKeepFeasibility={() => setFeasibilityMessage(null)}
          onUndoFeasibility={() => {
            if (!lastAddedClientId) {
              setFeasibilityMessage(null);
              return;
            }
            setCities((prev) =>
              removeCityByClientId(prev, lastAddedClientId),
            );
            setLastAddedClientId(null);
            setFeasibilityMessage(null);
          }}
        />
      )}

      {step === "days" && (
        <DaysPanel
          days={days}
          dayCount={demoTrip.day_count}
          complete={days.length >= demoTrip.day_count}
          onPlanNextDay={handlePlanNextDay}
          suggestPendingDay={suggestPendingDay}
          onAddPlace={(dayIndex, draft) => {
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
          }}
          onSuggestPlace={handleSuggestPlace}
          onRemovePlace={(dayIndex, placeIndex) => {
            setDays((prev) => removePlaceFromDays(prev, dayIndex, placeIndex));
          }}
        />
      )}
    </WizardLayout>
  );
}
