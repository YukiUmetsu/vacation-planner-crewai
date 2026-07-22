import { CreateTripForm } from "./CreateTripForm";
import { TripGist, TripGistEmpty } from "./TripGist";
import { TripPanel } from "./TripPanel";
import type { DayPlan, Route, Trip } from "../types/trip";

type Props = {
  demoMode: boolean;
  tripId: string | null;
  demoTrip: Trip;
  demoRoute: Route;
  demoDays: DayPlan[];
  onCreatedTrip: (id: string) => void;
  onGoToCities: () => void;
  onGoToDays: () => void;
  onOpenProfile: () => void;
};

/** Details step: create / demo intro + trip gist panel. */
export function DetailsStep({
  demoMode,
  tripId,
  demoTrip,
  demoRoute,
  demoDays,
  onCreatedTrip,
  onGoToCities,
  onGoToDays,
  onOpenProfile,
}: Props) {
  return (
    <div className="grid gap-8 lg:grid-cols-2 lg:gap-10">
      <section className="rounded-2xl border border-line/80 bg-surface/90 p-6 shadow-sm sm:p-8">
        {demoMode ? (
          <DemoDetailsIntro
            onGoToCities={onGoToCities}
            onGoToDays={onGoToDays}
            onOpenProfile={onOpenProfile}
          />
        ) : (
          <CreateTripForm onCreated={onCreatedTrip} />
        )}
      </section>
      <section className="rounded-2xl border border-line/80 bg-surface/90 p-6 shadow-sm sm:p-8">
        {demoMode ? (
          <TripGist
            trip={demoTrip}
            route={demoRoute}
            days={demoDays}
            onContinueToCities={onGoToCities}
            onContinueToDays={onGoToDays}
          />
        ) : tripId ? (
          <TripPanel
            tripId={tripId}
            onContinueToCities={onGoToCities}
            onContinueToDays={onGoToDays}
          />
        ) : (
          <TripGistEmpty />
        )}
      </section>
    </div>
  );
}

function DemoDetailsIntro({
  onGoToCities,
  onGoToDays,
  onOpenProfile,
}: {
  onGoToCities: () => void;
  onGoToDays: () => void;
  onOpenProfile: () => void;
}) {
  return (
    <div className="space-y-4">
      <h2 className="font-display text-2xl font-semibold text-ink">
        Demo trip loaded
      </h2>
      <p className="text-sm text-ink-muted">
        Use the step rail, or open <strong>Profile</strong> for preferences,
        energy level, and places you’ve been. On Days:{" "}
        <strong>Add place</strong> / <strong>Suggest a place</strong>. Create-trip
        API is available when demo mode is off (
        <code className="text-xs">VITE_USE_DEMO_DATA=false</code>).
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-lg bg-teal px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-deep"
          onClick={onGoToCities}
        >
          Go to cities
        </button>
        <button
          type="button"
          className="rounded-lg border border-teal bg-surface px-4 py-2.5 text-sm font-semibold text-teal hover:bg-teal-soft"
          onClick={onGoToDays}
        >
          Go to days
        </button>
        <button
          type="button"
          className="rounded-lg border border-line bg-surface px-4 py-2.5 text-sm font-semibold text-ink hover:bg-sand"
          onClick={onOpenProfile}
        >
          Open profile
        </button>
      </div>
    </div>
  );
}
