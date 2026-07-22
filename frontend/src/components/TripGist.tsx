import type { DayPlan, Route, Trip } from "../types/trip";

type Props = {
  trip: Trip;
  route: Route | null;
  days: DayPlan[];
  onContinueToCities?: () => void;
  onContinueToDays?: () => void;
};

export function TripGist({
  trip,
  route,
  days,
  onContinueToCities,
  onContinueToDays,
}: Props) {
  const confirmed =
    route?.status === "confirmed" || trip.destination_type === "city";
  const planned = days.length;
  const total = trip.day_count;

  return (
    <div className="flex h-full flex-col">
      <h2 className="font-display text-2xl font-semibold text-ink">Trip gist</h2>
      <p className="mt-1 text-sm text-ink-muted">
        {trip.origin} → {trip.destination} · {trip.start_date} – {trip.end_date} ·{" "}
        <span className="capitalize">{trip.status.replaceAll("_", " ")}</span>
      </p>

      {!route && trip.destination_type !== "city" && (
        <div className="mt-8 rounded-xl border border-dashed border-line bg-sand/50 p-6 text-sm text-ink-muted">
          <p>No city route yet.</p>
          {onContinueToCities && (
            <button
              type="button"
              onClick={onContinueToCities}
              className="mt-3 font-semibold text-teal underline-offset-2 hover:underline"
            >
              Continue to cities →
            </button>
          )}
        </div>
      )}

      {route && (
        <div className="mt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            {confirmed ? "Confirmed route" : "Proposed route"}
          </p>
          <ol className="mt-3 space-y-3 border-l-2 border-teal-soft pl-4">
            {route.cities.map((stop, i) => (
              <li key={`${stop.city}-${i}`} className="relative">
                <span className="absolute -left-[1.4rem] top-1.5 h-2.5 w-2.5 rounded-full bg-teal" />
                <p className="font-display text-lg font-semibold text-ink">
                  {stop.city}
                  <span className="ml-2 font-sans text-sm font-medium text-ink-muted">
                    {stop.nights} {stop.nights === 1 ? "night" : "nights"}
                  </span>
                </p>
                {stop.reason && (
                  <p className="text-sm text-ink-muted">{stop.reason}</p>
                )}
              </li>
            ))}
          </ol>
          {route.rationale && (
            <p className="mt-4 text-sm italic text-ink-muted">{route.rationale}</p>
          )}
          {!confirmed && onContinueToCities && (
            <button
              type="button"
              onClick={onContinueToCities}
              className="mt-4 font-semibold text-teal underline-offset-2 hover:underline"
            >
              Review cities →
            </button>
          )}
        </div>
      )}

      <div className="mt-auto flex items-center justify-between border-t border-line pt-4 text-sm">
        <span className="text-ink-muted">
          {planned} / {total} days planned
        </span>
        {confirmed && onContinueToDays && (
          <button
            type="button"
            onClick={onContinueToDays}
            className="font-semibold text-teal underline-offset-2 hover:underline"
          >
            Continue to days →
          </button>
        )}
      </div>
    </div>
  );
}

export function TripGistEmpty() {
  return (
    <div className="flex h-full min-h-64 flex-col items-center justify-center text-center">
      <h2 className="font-display text-2xl font-semibold text-ink">
        Your itinerary appears here
      </h2>
      <p className="mt-2 max-w-xs text-sm text-ink-muted">
        Add your trip details to get started. City nights and day plans will show
        up in this panel.
      </p>
      <div
        className="mt-8 h-28 w-40 opacity-40"
        aria-hidden
        style={{
          backgroundImage:
            "radial-gradient(circle at 30% 40%, #0d5c5f33 0 8%, transparent 9%), radial-gradient(circle at 70% 55%, #0d5c5f33 0 6%, transparent 7%)",
        }}
      />
    </div>
  );
}
