import { DetailsStep } from "./components/DetailsStep";
import { ProfileScreen } from "./components/ProfileScreen";
import { TripStatusBanner } from "./components/TripStatusBanner";
import { WizardLayout } from "./components/WizardLayout";
import { CitiesPanel } from "./components/cities/CitiesPanel";
import { DaysPanel } from "./components/days/DaysPanel";
import { useTripWizard } from "./hooks/useTripWizard";

/**
 * DEMO MODE (default): browse UI with static Japan data + profile.
 * Set VITE_USE_DEMO_DATA=false (or pass demoMode={false}) for the live create flow.
 */
const DEFAULT_DEMO_MODE = import.meta.env.VITE_USE_DEMO_DATA !== "false";

export type AppProps = {
  /** Override env default — used by tests for the live create path. */
  demoMode?: boolean;
};

export function App({ demoMode = DEFAULT_DEMO_MODE }: AppProps) {
  const wizard = useTripWizard(demoMode);

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
      onStepChange={demoMode ? wizard.setStep : undefined}
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
          demoTrip={wizard.demoTrip}
          demoRoute={wizard.demoRoute}
          demoDays={wizard.demoDays}
          onCreatedTrip={wizard.handleCreatedTrip}
          onGoToCities={() => void wizard.goToCities()}
          onGoToDays={() => void wizard.goToDays()}
          onOpenProfile={() => wizard.setScreen("profile")}
        />
      )}

      {wizard.step === "cities" && (
        <CitiesPanel
          cities={wizard.cities}
          checkingCity={wizard.checkingCity}
          feasibilityMessage={wizard.feasibilityMessage}
          proposePending={wizard.proposePending}
          confirmPending={wizard.confirmPending}
          onNightsChange={wizard.handleNightsChange}
          onAddCity={wizard.handleAddCity}
          onPropose={wizard.handlePropose}
          onConfirm={() => void wizard.handleConfirm()}
          onKeepFeasibility={wizard.handleKeepFeasibility}
          onUndoFeasibility={wizard.handleUndoFeasibility}
        />
      )}

      {wizard.step === "days" && (
        <DaysPanel
          days={wizard.days}
          dayCount={wizard.dayCount}
          energyLevel={wizard.profile.energyLevel}
          complete={wizard.days.length >= wizard.dayCount}
          pending={wizard.planPending}
          onPlanNextDay={wizard.handlePlanNextDay}
          suggestPendingDay={wizard.suggestPendingDay}
          onAddPlace={wizard.handleAddPlace}
          onSuggestPlace={
            demoMode ? wizard.handleSuggestPlace : undefined
          }
          onRemovePlace={wizard.handleRemovePlace}
        />
      )}
    </WizardLayout>
  );
}
