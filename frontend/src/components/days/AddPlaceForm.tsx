import { useState } from "react";
import { allocateUniquePlaceKey } from "../../lib/dayPlaces";
import type { Place } from "../../types/trip";

export type PlaceDraft = {
  name: string;
  category?: string;
  reason_to_visit?: string;
};

type Props = {
  /** LEARNING / demo: append a place the user typed */
  onAdd?: (place: PlaceDraft) => void;
  /** LEARNING / demo: ask crew/API for a suggestion */
  onSuggest?: () => void;
  suggestPending?: boolean;
};

const fieldClass =
  "mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-teal focus:ring-2 focus:ring-teal-soft";

export function AddPlaceForm({ onAdd, onSuggest, suggestPending }: Props) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [category, setCategory] = useState("other");
  const [reason, setReason] = useState("");

  if (!open) {
    return (
      <div className="mt-3 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="text-sm font-semibold text-teal hover:underline"
        >
          + Add place
        </button>
        <button
          type="button"
          onClick={onSuggest}
          disabled={!onSuggest || suggestPending}
          className="text-sm font-semibold text-teal hover:underline disabled:opacity-40"
        >
          {suggestPending ? "Suggesting…" : "Suggest a place"}
        </button>
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
        <div className="flex gap-2 pt-1">
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
              setOpen(false);
            }}
          >
            Add
          </button>
          <button
            type="button"
            className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-semibold text-ink-muted"
            onClick={() => setOpen(false)}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

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
