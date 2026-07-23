import { useState } from "react";
import { isTripIncomplete, tripStatusLabel } from "../lib/tripStatus";
import type { Trip } from "../types/trip";

type Props = {
  trips: Trip[];
  activeTripId: string | null;
  loading?: boolean;
  deletingTripId?: string | null;
  onSelectTrip: (tripId: string) => void;
  onDeleteTrip: (tripId: string) => void | Promise<void>;
  onStartNew: () => void;
};

/**
 * Interactive trip list for the details step — select to edit, confirm to remove.
 */
export function TripSwitcher({
  trips,
  activeTripId,
  loading = false,
  deletingTripId = null,
  onSelectTrip,
  onDeleteTrip,
  onStartNew,
}: Props) {
  const [confirmId, setConfirmId] = useState<string | null>(null);

  if (loading && trips.length === 0) {
    return (
      <section className="trip-switcher mb-8" aria-busy="true" aria-label="Your trips">
        <header className="mb-4 flex items-end justify-between gap-3">
          <div>
            <p className="font-display text-2xl font-semibold text-ink">Your trips</p>
            <p className="mt-0.5 text-sm text-ink-muted">Loading saved plans…</p>
          </div>
        </header>
        <div className="h-24 rounded-2xl bg-sand-deep/40" />
      </section>
    );
  }

  if (trips.length === 0) {
    return null;
  }

  const drafting = !activeTripId;

  return (
    <section className="trip-switcher mb-8" aria-label="Your trips">
      <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-display text-2xl font-semibold text-ink">Your trips</p>
          <p className="mt-0.5 text-sm text-ink-muted">
            Open one to edit, or start fresh.
          </p>
        </div>
        <button
          type="button"
          onClick={onStartNew}
          className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${
            drafting
              ? "bg-teal text-white"
              : "border border-line bg-surface text-teal hover:bg-teal-soft"
          }`}
          aria-current={drafting ? "page" : undefined}
        >
          + New trip
        </button>
      </header>

      <ul className="divide-y divide-line/70 overflow-hidden rounded-2xl border border-line/80 bg-surface/80 shadow-sm">
        {trips.map((trip) => {
          const active = trip.trip_id === activeTripId;
          const incomplete = isTripIncomplete(trip);
          const confirming = confirmId === trip.trip_id;
          const deleting = deletingTripId === trip.trip_id;

          return (
            <li
              key={trip.trip_id}
              className={`trip-switcher-row relative transition ${
                active ? "bg-teal-soft/55" : "hover:bg-sand/60"
              }`}
            >
              {active && (
                <span
                  className="absolute inset-y-3 left-0 w-1 rounded-r-full bg-teal"
                  aria-hidden
                />
              )}

              {confirming ? (
                <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3.5 sm:px-5">
                  <p className="text-sm text-ink">
                    Remove <span className="font-semibold">{trip.destination}</span>?
                    This cannot be undone.
                  </p>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={deleting}
                      onClick={() => setConfirmId(null)}
                      className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-semibold text-ink hover:bg-sand"
                    >
                      Keep
                    </button>
                    <button
                      type="button"
                      disabled={deleting}
                      onClick={() => {
                        void Promise.resolve(onDeleteTrip(trip.trip_id)).finally(() => {
                          setConfirmId(null);
                        });
                      }}
                      className="rounded-lg bg-warn px-3 py-1.5 text-sm font-semibold text-white hover:bg-warn/90 disabled:opacity-60"
                    >
                      {deleting ? "Removing…" : "Remove"}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-stretch gap-1">
                  <button
                    type="button"
                    onClick={() => onSelectTrip(trip.trip_id)}
                    className="min-w-0 flex-1 px-4 py-3.5 text-left sm:px-5"
                    aria-current={active ? "page" : undefined}
                  >
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <span className="font-display text-xl font-semibold text-ink sm:text-2xl">
                        {trip.destination}
                      </span>
                      <span
                        className={`text-xs font-semibold capitalize tracking-wide ${
                          incomplete ? "text-teal" : "text-ink-muted"
                        }`}
                      >
                        {incomplete
                          ? tripStatusLabel(trip.status)
                          : "Complete"}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-ink-muted">
                      {trip.origin} → {trip.destination}
                      <span className="mx-1.5 text-line" aria-hidden>
                        ·
                      </span>
                      {trip.start_date} – {trip.end_date}
                      <span className="mx-1.5 text-line" aria-hidden>
                        ·
                      </span>
                      {trip.day_count} {trip.day_count === 1 ? "day" : "days"}
                    </p>
                    {active && (
                      <p className="mt-1.5 text-xs font-semibold text-teal">
                        Editing now
                      </p>
                    )}
                  </button>

                  <div className="flex shrink-0 flex-col justify-center gap-1 py-2 pr-3 sm:pr-4">
                    {!active && (
                      <button
                        type="button"
                        onClick={() => onSelectTrip(trip.trip_id)}
                        className="rounded-lg px-2.5 py-1.5 text-xs font-semibold text-teal hover:bg-teal-soft"
                      >
                        Edit
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => setConfirmId(trip.trip_id)}
                      disabled={deleting}
                      className="rounded-lg px-2.5 py-1.5 text-xs font-semibold text-ink-muted hover:bg-sand-deep/50 hover:text-warn"
                      aria-label={`Remove ${trip.destination}`}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
