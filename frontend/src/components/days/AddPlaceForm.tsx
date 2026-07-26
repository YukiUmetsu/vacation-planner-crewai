import { useEffect, useState } from "react";
import { allocateUniquePlaceKey } from "../../lib/dayPlaces";
import { cityImageUrl } from "../../lib/travelAtmosphere";
import type { Place } from "../../types/trip";
import { CityThumb } from "../cities/CityThumb";

export type PlaceDraft = {
  name: string;
  category?: string;
  reason_to_visit?: string;
};

type Props = {
  /** Overnight city for this day — used in suggest loading imagery/copy. */
  city?: string;
  destination?: string;
  /** Append a place the user typed */
  onAdd?: (place: PlaceDraft) => void;
  /** Request a place suggestion (demo or API); optional preference hint. */
  onSuggest?: (hint?: string) => void;
  suggestPending?: boolean;
  /** True while plan-next-day is in flight — suggest is blocked server-side. */
  dayPlanningPending?: boolean;
};

type Panel = "closed" | "add" | "suggest";

const fieldClass =
  "mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-teal focus:ring-2 focus:ring-teal-soft";

function suggestWaitCopy(elapsedSec: number, city: string): string {
  if (elapsedSec < 15) return `Finding a spot in ${city}…`;
  if (elapsedSec < 40) return `Still searching ${city} for a good fit…`;
  return `Taking a bit longer for ${city} — almost there.`;
}

export function AddPlaceForm({
  city = "",
  destination = "",
  onAdd,
  onSuggest,
  suggestPending,
  dayPlanningPending,
}: Props) {
  const [panel, setPanel] = useState<Panel>("closed");
  const [name, setName] = useState("");
  const [category, setCategory] = useState("other");
  const [reason, setReason] = useState("");
  const [hint, setHint] = useState("");
  const [elapsedSec, setElapsedSec] = useState(0);

  const cityLabel = city.trim() || "this day";
  const suggestBlocked = Boolean(suggestPending || dayPlanningPending);

  useEffect(() => {
    if (!suggestPending) {
      setElapsedSec(0);
      return;
    }
    const started = Date.now();
    const id = window.setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    return () => window.clearInterval(id);
  }, [suggestPending]);

  useEffect(() => {
    if (dayPlanningPending && panel === "suggest") {
      setHint("");
      setPanel("closed");
    }
  }, [dayPlanningPending, panel]);

  function resetSuggest() {
    setHint("");
    setPanel("closed");
  }

  if (panel === "closed") {
    return (
      <div className="mt-3 space-y-3">
        {suggestPending ? (
          <div
            className="flex items-center gap-3 overflow-hidden rounded-xl border border-line/80 bg-sand/40 p-3"
            role="status"
            aria-live="polite"
            aria-busy="true"
          >
            <CityThumb
              city={cityLabel}
              imageUrl={cityImageUrl(cityLabel, destination)}
              className="h-12 w-12"
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-ink">
                Suggesting a place
              </p>
              <p className="text-xs text-ink-muted">
                {suggestWaitCopy(elapsedSec, cityLabel)}
              </p>
              <div className="propose-loading-shimmer mt-2 h-1 overflow-hidden rounded-full bg-line/60">
                <div className="propose-loading-shimmer-bar h-full w-1/3 rounded-full bg-teal/70" />
              </div>
            </div>
          </div>
        ) : null}
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => setPanel("add")}
            disabled={suggestBlocked}
            className="text-sm font-semibold text-teal hover:underline disabled:opacity-40 disabled:no-underline"
          >
            + Add place
          </button>
          {onSuggest ? (
            <button
              type="button"
              onClick={() => setPanel("suggest")}
              disabled={suggestBlocked}
              title={
                dayPlanningPending
                  ? "Available after day planning finishes"
                  : undefined
              }
              className="text-sm font-semibold text-teal hover:underline disabled:cursor-not-allowed disabled:opacity-40 disabled:no-underline"
            >
              {suggestPending ? "Suggesting…" : "Suggest a place"}
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  if (panel === "suggest") {
    return (
      <div className="mt-3 rounded-xl border border-line bg-sand/40 p-3">
        <p className="text-sm font-semibold text-ink">Suggest a place</p>
        <p className="mt-0.5 text-xs text-ink-muted">
          Optional preference steers the next stop (e.g. quiet park, ramen,
          bookstore). Leave blank for a general pick.
        </p>
        <label className="mt-3 block text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Preference (optional)
          <input
            className={fieldClass}
            value={hint}
            onChange={(e) => setHint(e.target.value)}
            placeholder="e.g. a quiet park"
            autoFocus
            disabled={suggestBlocked}
            onKeyDown={(e) => {
              if (e.key === "Enter" && onSuggest && !suggestBlocked) {
                e.preventDefault();
                onSuggest(hint.trim() || undefined);
                resetSuggest();
              }
            }}
          />
        </label>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-lg bg-teal px-3 py-1.5 text-sm font-semibold text-white hover:bg-teal-deep disabled:cursor-not-allowed disabled:opacity-50"
            disabled={suggestBlocked || !onSuggest}
            onClick={() => {
              onSuggest?.(hint.trim() || undefined);
              resetSuggest();
            }}
          >
            {suggestPending ? "Suggesting…" : "Suggest"}
          </button>
          <button
            type="button"
            className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-semibold text-ink-muted"
            disabled={suggestPending}
            onClick={resetSuggest}
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-3 rounded-xl border border-line bg-sand/40 p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
        Add a place
      </p>
      <div className="mt-2 space-y-2">
        <label className="block text-xs font-semibold text-ink-muted">
          Name
          <input
            className={fieldClass}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Meiji Shrine"
            autoFocus
          />
        </label>
        <label className="block text-xs font-semibold text-ink-muted">
          Category
          <select
            className={fieldClass}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="food">Food</option>
            <option value="culture">Culture</option>
            <option value="nature">Nature</option>
            <option value="amusement">Amusement</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label className="block text-xs font-semibold text-ink-muted">
          Why visit (optional)
          <input
            className={fieldClass}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Short note"
          />
        </label>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-lg bg-teal px-3 py-1.5 text-sm font-semibold text-white hover:bg-teal-deep disabled:opacity-50"
          disabled={!name.trim() || !onAdd}
          onClick={() => {
            onAdd?.({
              name: name.trim(),
              category,
              reason_to_visit: reason.trim() || undefined,
            });
            setName("");
            setReason("");
            setCategory("other");
            setPanel("closed");
          }}
        >
          Add
        </button>
        <button
          type="button"
          className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-semibold text-ink-muted"
          onClick={() => setPanel("closed")}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

/** Build a Place from a manual draft (demo / local add). */
export function placeFromDraft(
  draft: PlaceDraft,
  order: number,
  existingKeys: Iterable<string> = [],
): Place {
  return {
    name: draft.name,
    category: draft.category,
    reason_to_visit: draft.reason_to_visit,
    order_in_day: order,
    place_key: allocateUniquePlaceKey(draft.name, existingKeys, order),
  };
}
