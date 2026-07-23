import { useEffect } from "react";
import { DetailsStep } from "./components/DetailsStep";
import { DevCrewModeSwitch } from "./components/DevCrewModeSwitch";
import { ProfileScreen } from "./components/ProfileScreen";
import { TripStatusBanner } from "./components/TripStatusBanner";
import { WizardLayout, type WizardStep } from "./components/WizardLayout";
import { CitiesPanel } from "./components/cities/CitiesPanel";
import { DaysPanel } from "./components/days/DaysPanel";
import { useTripWizard } from "./hooks/useTripWizard";
import { overnightCityForDay } from "./lib/cityRoute";
import {
  ensureIdToken,
  isCognitoConfigured,
  isSignedIn,
  LandingPage,
} from "./auth";

/**
 * DEMO MODE (default): browse UI with static Japan data + profile.
 * Set VITE_USE_DEMO_DATA=false (or pass demoMode={false}) for the live create flow.
 */
const DEFAULT_DEMO_MODE = import.meta.env.VITE_USE_DEMO_DATA !== "false";

export type AppProps = {
  /** Override env default — used by tests for the live create path. */
  demoMode?: boolean;
};

/** Live + Cognito configured requires a session before the trip wizard. */
export function requiresAuthGate(demoMode: boolean): boolean {
  return !demoMode && isCognitoConfigured() && !isSignedIn();
}

export function App({ demoMode = DEFAULT_DEMO_MODE }: AppProps) {
  const devChrome = import.meta.env.DEV === true;
  return (
    <>
      <DevCrewModeSwitch />
      <div className={devChrome ? "dev-crew-chrome-pad" : undefined}>
        {requiresAuthGate(demoMode) ? (
          <LandingPage />
        ) : (
          <TripApp demoMode={demoMode} />
        )}
      </div>
    </>
  );
}

function TripApp({ demoMode }: { demoMode: boolean }) {
  // Soft-expired id tokens still pass the gate when refresh_token exists; refresh now
  // so the first API call does not race the authorizer.
  useEffect(() => {
    if (demoMode || !isCognitoConfigured()) return;
    void ensureIdToken();
  }, [demoMode]);

  const wizard = useTripWizard(demoMode);

  function handleWizardStepChange(next: WizardStep) {
    // Live mode: only allow going back to earlier steps (not skipping ahead).
    const order = ["details", "cities", "days"] as const;
    const cur = order.indexOf(wizard.step);
    const tgt = order.indexOf(next);
    if (tgt < 0 || tgt > cur) return;
    if (next === "details") wizard.goToDetails();
    else if (next === "cities") void wizard.goToCities();
    else wizard.setStep(next);
  }

  if (wizard.screen === "profile") {
    return (
      <ProfileScreen
        demoMode={demoMode}
        profile={wizard.profile}
        onChange={wizard.updateProfile}
        onBack={() => wizard.setScreen("trip")}
      />
    );
  }

  return (
    <WizardLayout
      step={wizard.step}
      onStepChange={demoMode ? wizard.setStep : handleWizardStepChange}
      demoBadge={demoMode}
      onOpenProfile={() => wizard.setScreen("profile")}
    >
      <TripStatusBanner
        hydrating={wizard.hydrating}
        actionError={wizard.actionError}
      />

      {wizard.step === "details" && (
        <DetailsStep
          demoMode={demoMode}
          tripId={wizard.tripId}
          liveTrip={wizard.liveTrip}
          tripsList={wizard.tripsList}
          tripsLoading={wizard.tripsLoading}
          deletingTripId={wizard.deletingTripId}
          demoTrip={wizard.demoTrip}
          demoRoute={wizard.demoRoute}
          demoDays={wizard.demoDays}
          onCreatedTrip={wizard.handleCreatedTrip}
          onUpdatedTrip={wizard.handleUpdatedTrip}
          onSelectTrip={(id) => void wizard.selectTrip(id)}
          onDeleteTrip={(id) => void wizard.removeTrip(id)}
          onStartNewTrip={wizard.startNewTrip}
          onGoToCities={() => void wizard.goToCities()}
          onGoToDays={() => void wizard.goToDays()}
          onOpenProfile={() => wizard.setScreen("profile")}
        />
      )}

      {wizard.step === "cities" && (
        <CitiesPanel
          cities={wizard.cities}
          dayCount={wizard.dayCount}
          destination={wizard.destination}
          checkingCity={wizard.checkingCity}
          feasibilityMessage={wizard.feasibilityMessage}
          proposePending={wizard.proposePending}
          confirmPending={wizard.confirmPending}
          onNightsChange={wizard.handleNightsChange}
          onRemoveCity={wizard.handleRemoveCity}
          onAddCity={wizard.handleAddCity}
          onPropose={wizard.handlePropose}
          onConfirm={() => void wizard.handleConfirm()}
          onBackToDetails={wizard.goToDetails}
          onKeepFeasibility={wizard.handleKeepFeasibility}
          onUndoFeasibility={wizard.handleUndoFeasibility}
        />
      )}

      {wizard.step === "days" && (
        <DaysPanel
          days={wizard.days}
          dayCount={wizard.dayCount}
          destination={wizard.destination}
          planningCity={
            overnightCityForDay(
              wizard.cities,
              wizard.liveTrip?.planning_day_index ??
                wizard.liveTrip?.next_day_index ??
                wizard.days.length + 1,
            ) ??
            wizard.cities[wizard.cities.length - 1]?.city ??
            wizard.destination
          }
          energyLevel={wizard.profile.energyLevel}
          pending={wizard.planPending}
          complete={wizard.days.length >= wizard.dayCount}
          suggestPendingDay={wizard.suggestPendingDay}
          onPlanNextDay={() => void wizard.handlePlanNextDay()}
          onAddPlace={demoMode ? wizard.handleAddPlace : undefined}
          onSuggestPlace={wizard.handleSuggestPlace}
          onRemovePlace={wizard.handleRemovePlace}
          onRemoveDay={wizard.handleRemoveDay}
        />
      )}
    </WizardLayout>
  );
}
