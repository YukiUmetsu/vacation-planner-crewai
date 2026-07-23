import { useMemo } from "react";
import { CreateTripForm } from "./CreateTripForm";
import { TripGist, TripGistEmpty } from "./TripGist";
import { TripPanel } from "./TripPanel";
import { TripSwitcher } from "./TripSwitcher";
import type { CreateTripInput, DayPlan, Route, Trip } from "../types/trip";

type Props = {
  demoMode: boolean;
  tripId: string | null;
  liveTrip?: Trip | null;
  tripsList?: Trip[];
  tripsLoading?: boolean;
  demoTrip: Trip;
  demoRoute: Route;
  demoDays: DayPlan[];
  onCreatedTrip: (id: string) => void | Promise<void>;
  onUpdatedTrip?: (id: string) => void | Promise<void>;
  onSelectTrip?: (id: string) => void;
  onDeleteTrip?: (id: string) => void | Promise<void>;
  onStartNewTrip?: () => void;
  deletingTripId?: string | null;
  onGoToCities: () => void;
  onGoToDays: () => void;
  onOpenProfile: () => void;
};

/** Details step: create / edit trip meta + trip gist panel. */
export function DetailsStep({
  demoMode,
  tripId,
  liveTrip,
  tripsList = [],
  tripsLoading = false,
  deletingTripId = null,
  demoTrip,
  demoRoute,
  demoDays,
  onCreatedTrip,
  onUpdatedTrip,
  onSelectTrip,
  onDeleteTrip,
  onStartNewTrip,
  onGoToCities,
  onGoToDays,
  onOpenProfile,
}: Props) {
  const editValues = useMemo((): CreateTripInput | undefined => {
    if (!liveTrip) return undefined;
    return {
      origin: liveTrip.origin,
      destination: liveTrip.destination,
      destination_type: liveTrip.destination_type,
      start_date: liveTrip.start_date,
      end_date: liveTrip.end_date,
      preferences: liveTrip.preferences ?? "",
    };
  }, [liveTrip]);

  return (
    <div>
      {!demoMode && onSelectTrip && onStartNewTrip && onDeleteTrip && (
        <TripSwitcher
          trips={tripsList}
          activeTripId={tripId}
          loading={tripsLoading}
          deletingTripId={deletingTripId}
          onSelectTrip={onSelectTrip}
          onDeleteTrip={onDeleteTrip}
          onStartNew={onStartNewTrip}
        />
      )}

      <div className="grid gap-8 lg:grid-cols-2 lg:gap-10">
        <section className="rounded-2xl border border-line/80 bg-surface/90 p-6 shadow-sm sm:p-8">
          {demoMode ? (
            <DemoDetailsIntro
              onGoToCities={onGoToCities}
              onGoToDays={onGoToDays}
              onOpenProfile={onOpenProfile}
            />
          ) : (
            <CreateTripForm
              key={tripId ?? "new"}
              tripId={tripId}
              initialValues={editValues}
              onCreated={onCreatedTrip}
              onUpdated={onUpdatedTrip}
            />
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
