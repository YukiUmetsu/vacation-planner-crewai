import { useState } from "react";

type Props = {
  /** Append city to the draft route (parent may run a feasibility check afterward). */
  onAdd?: (city: string, reason: string) => void;
};

export function AddCityForm({ onAdd }: Props) {
  const [open, setOpen] = useState(false);
  const [city, setCity] = useState("");
  const [reason, setReason] = useState("");

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-2 inline-flex items-center gap-1.5 text-sm font-semibold text-teal hover:underline"
      >
        <span aria-hidden>+</span> Add city
      </button>
    );
  }

  return (
    <div className="mt-4 rounded-xl border border-line bg-sand/40 p-4">
      <p className="text-sm font-semibold text-ink">Add a stop</p>
      <p className="mt-0.5 text-xs text-ink-muted">
        Suggest another city on your route.
      </p>
      <div className="mt-3 space-y-3">
        <label className="block text-xs font-semibold uppercase tracking-wide text-ink-muted">
          City name
          <input
            className="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-teal focus:ring-2 focus:ring-teal-soft"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            placeholder="e.g. Hiroshima"
            autoFocus
          />
        </label>
        <label className="block text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Reason (optional)
          <input
            className="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-teal focus:ring-2 focus:ring-teal-soft"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why stop here?"
          />
        </label>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded-lg bg-teal px-3 py-2 text-sm font-semibold text-white hover:bg-teal-deep disabled:opacity-50"
            disabled={!city.trim() || !onAdd}
            onClick={() => {
              onAdd?.(city.trim(), reason.trim());
              setCity("");
              setReason("");
              setOpen(false);
            }}
          >
            Add
          </button>
          <button
            type="button"
            className="rounded-lg border border-line bg-surface px-3 py-2 text-sm font-semibold text-ink-muted hover:border-teal/40"
            onClick={() => {
              setOpen(false);
              setCity("");
              setReason("");
            }}
          >
            Cancel
          </button>
        </div>
        {!onAdd && (
          <p className="text-xs text-ink-muted">
            Pass <code className="text-teal">onAdd</code> from the Cities step to enable
            saving.
          </p>
        )}
      </div>
    </div>
  );
}
