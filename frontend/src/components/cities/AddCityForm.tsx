import { useState } from "react";

type Props = {
  /** Append city to the draft route (parent may run a feasibility check afterward). */
  onAdd?: (city: string, reason: string) => void;
  /** GenAI suggest — parent inserts candidate into draft. */
  onSuggest?: (hint?: string) => void;
  suggestPending?: boolean;
  /** When set, hide the add affordance or show why adding is blocked. */
  disabledReason?: string;
};

type Panel = "closed" | "add" | "suggest";

/**
 * Draft-route city add / suggest.
 * Suggest opens its own panel with an optional preference hint (not a one-click fire).
 */
export function AddCityForm({
  onAdd,
  onSuggest,
  suggestPending = false,
  disabledReason,
}: Props) {
  const [panel, setPanel] = useState<Panel>("closed");
  const [city, setCity] = useState("");
  const [reason, setReason] = useState("");
  const [hint, setHint] = useState("");

  function reset() {
    setCity("");
    setReason("");
    setHint("");
    setPanel("closed");
  }

  if (disabledReason && !onAdd && !onSuggest) {
    return (
      <p className="mt-2 text-sm text-ink-muted" role="status">
        {disabledReason}
      </p>
    );
  }

  if (panel === "closed") {
    return (
      <div className="mt-2 flex flex-wrap items-center gap-3">
        {onAdd ? (
          <button
            type="button"
            onClick={() => setPanel("add")}
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-teal hover:underline"
          >
            <span aria-hidden>+</span> Add city
          </button>
        ) : null}
        {onSuggest ? (
          <button
            type="button"
            disabled={suggestPending}
            onClick={() => setPanel("suggest")}
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-teal hover:underline disabled:opacity-50"
          >
            {suggestPending ? "Suggesting…" : "Suggest a city"}
          </button>
        ) : null}
        {disabledReason && !onAdd ? (
          <p className="text-sm text-ink-muted" role="status">
            {disabledReason}
          </p>
        ) : null}
      </div>
    );
  }

  if (panel === "suggest") {
    return (
      <div className="mt-4 rounded-xl border border-line bg-sand/40 p-4">
        <p className="text-sm font-semibold text-ink">Suggest a city</p>
        <p className="mt-0.5 text-xs text-ink-muted">
          Optional preference steers the suggestion (e.g. coastal, food town,
          quieter base). Leave blank for a general pick.
        </p>
        <label className="mt-3 block text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Preference (optional)
          <input
            className="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-teal focus:ring-2 focus:ring-teal-soft"
            value={hint}
            onChange={(e) => setHint(e.target.value)}
            placeholder="e.g. somewhere coastal"
            autoFocus
            disabled={suggestPending}
            onKeyDown={(e) => {
              if (e.key === "Enter" && onSuggest && !suggestPending) {
                e.preventDefault();
                onSuggest(hint.trim() || undefined);
                reset();
              }
            }}
          />
        </label>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-lg bg-teal px-3 py-2 text-sm font-semibold text-white hover:bg-teal-deep disabled:opacity-50"
            disabled={suggestPending || !onSuggest}
            onClick={() => {
              onSuggest?.(hint.trim() || undefined);
              reset();
            }}
          >
            {suggestPending ? "Suggesting…" : "Suggest"}
          </button>
          <button
            type="button"
            className="rounded-lg border border-line bg-surface px-3 py-2 text-sm font-semibold text-ink-muted hover:border-teal/40"
            disabled={suggestPending}
            onClick={reset}
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-4 rounded-xl border border-line bg-sand/40 p-4">
      <p className="text-sm font-semibold text-ink">Add a stop</p>
      <p className="mt-0.5 text-xs text-ink-muted">
        Type a city to add manually to your draft route.
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
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-lg bg-teal px-3 py-2 text-sm font-semibold text-white hover:bg-teal-deep disabled:opacity-50"
            disabled={!city.trim() || !onAdd}
            onClick={() => {
              onAdd?.(city.trim(), reason.trim());
              reset();
            }}
          >
            Add
          </button>
          <button
            type="button"
            className="rounded-lg border border-line bg-surface px-3 py-2 text-sm font-semibold text-ink-muted hover:border-teal/40"
            onClick={reset}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
