import type { CityStop } from "../../types/trip";
import { AddCityForm } from "./AddCityForm";
import { CityStopRow } from "./CityStopRow";
import { FeasibilityBanner } from "./FeasibilityBanner";

type Props = {
  cities: CityStop[];
  feasibilityMessage?: string | null;
  checkingCity?: string | null;
  /** LEARNING: wire these from App / Cities step */
  onPropose?: () => void;
  onConfirm?: () => void;
  onNightsChange?: (index: number, nights: number) => void;
  onAddCity?: (city: string, reason: string) => void;
  onKeepFeasibility?: () => void;
  onUndoFeasibility?: () => void;
  proposePending?: boolean;
  confirmPending?: boolean;
};

/**
 * Presentational Cities step chrome (mockup-aligned).
 * LEARNING: create a parent that owns draft route + mutations, then pass props here.
 */
export function CitiesPanel({
  cities,
  feasibilityMessage,
  checkingCity,
  onPropose,
  onConfirm,
  onNightsChange,
  onAddCity,
  onKeepFeasibility,
  onUndoFeasibility,
  proposePending,
  confirmPending,
}: Props) {
  return (
    <section className="rounded-2xl border border-line/80 bg-surface/90 p-6 shadow-sm sm:p-8">
      <h2 className="font-display text-2xl font-semibold text-ink">
        Add or edit your cities
      </h2>
      <p className="mt-1 text-sm text-ink-muted">
        Review your route and adjust nights in each place.
      </p>

      <ol className="mt-2">
        {cities.map((stop, index) => (
          <CityStopRow
            key={`${stop.city}-${index}`}
            stop={stop}
            checking={checkingCity === stop.city}
            onNightsChange={
              onNightsChange
                ? (nights) => onNightsChange(index, nights)
                : undefined
            }
          />
        ))}
      </ol>

      <AddCityForm onAdd={onAddCity} />

      {feasibilityMessage && (
        <FeasibilityBanner
          message={feasibilityMessage}
          onKeep={onKeepFeasibility}
          onUndo={onUndoFeasibility}
        />
      )}

      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <button
          type="button"
          className="flex-1 rounded-lg border border-teal bg-surface px-4 py-3 text-sm font-semibold text-teal hover:bg-teal-soft disabled:opacity-50"
          disabled={!onPropose || proposePending}
          onClick={onPropose}
        >
          {proposePending ? "Proposing…" : "Propose cities"}
        </button>
        <button
          type="button"
          className="flex-1 rounded-lg bg-teal px-4 py-3 text-sm font-semibold text-white hover:bg-teal-deep disabled:opacity-50"
          disabled={!onConfirm || confirmPending}
          onClick={onConfirm}
        >
          {confirmPending ? "Confirming…" : "Confirm route"}
        </button>
      </div>

      {!onPropose && !onConfirm && (
        <p className="mt-4 text-xs text-ink-muted">
          {/* LEARNING */}
          Wire <code className="text-teal">onPropose</code> /{" "}
          <code className="text-teal">onConfirm</code> with TanStack mutations and
          invalidate <code className="text-teal">["trip", tripId]</code>.
        </p>
      )}
    </section>
  );
}
