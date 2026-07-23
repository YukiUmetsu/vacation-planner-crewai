import { useState } from "react";
import type { CityStop } from "../../types/trip";
import { CityThumb } from "./CityThumb";
import {
  CityPopularPopover,
  type CityHighlightCategory,
} from "./CityPopularPopover";

type Props = {
  stop: CityStop;
  imageUrl?: string | null;
  highlights?: CityHighlightCategory[];
  checking?: boolean;
  /** Upper bound for the + control (last city is usually locked). */
  maxNights?: number;
  /** When true, nights are derived from the trip window — hide +/-. */
  nightsLocked?: boolean;
  /** Update nights for this stop (parent recomputes day ranges). */
  onNightsChange?: (nights: number) => void;
  onRemove?: () => void;
};

const DEFAULT_HIGHLIGHTS: CityHighlightCategory[] = [
  { label: "Food", examples: "local markets, casual eats" },
  { label: "Culture", examples: "museums, historic sites" },
  { label: "Amusement", examples: "parks, nightlife" },
  { label: "Outdoors", examples: "walks, viewpoints" },
];

export function highlightsForStop(stop: CityStop): CityHighlightCategory[] {
  if (!stop.highlights?.length) return DEFAULT_HIGHLIGHTS;
  return [
    {
      label: "Highlights",
      examples: stop.highlights.slice(0, 6).join(", "),
    },
  ];
}

export function CityStopRow({
  stop,
  imageUrl,
  highlights,
  checking = false,
  maxNights,
  nightsLocked = false,
  onNightsChange,
  onRemove,
}: Props) {
  const [open, setOpen] = useState(false);
  const categories = highlights ?? highlightsForStop(stop);
  const canEditNights = Boolean(onNightsChange) && !nightsLocked;
  const atMax =
    typeof maxNights === "number" ? stop.nights >= maxNights : false;

  return (
    <li
      className="relative flex items-start gap-3 border-b border-line py-4 last:border-b-0"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) {
          setOpen(false);
        }
      }}
    >
      <div className="relative shrink-0">
        <button
          type="button"
          className="rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-teal"
          aria-describedby={open ? `popular-${stop.city}` : undefined}
        >
          <CityThumb city={stop.city} imageUrl={imageUrl} />
        </button>
        {open && (
          <div id={`popular-${stop.city}`}>
            <CityPopularPopover city={stop.city} categories={categories} />
          </div>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <p className="font-display text-lg font-semibold text-ink">{stop.city}</p>
        {stop.country ? (
          <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
            {stop.country}
          </p>
        ) : null}
        <p className="mt-0.5 text-xs text-ink-muted">
          Days {stop.arrival_day_index}–{stop.departure_day_index}
          {nightsLocked ? " · nights auto-fit to trip end" : null}
        </p>
        {stop.reason ? (
          <p className="mt-0.5 text-sm text-ink-muted">{stop.reason}</p>
        ) : null}
        {checking && (
          <p className="mt-1 text-xs text-ink-muted" role="status">
            Checking route…
          </p>
        )}
      </div>

      <div className="flex shrink-0 flex-col items-end gap-2">
        <div className="text-right">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Nights
          </p>
          <div className="mt-1 inline-flex items-center rounded-lg border border-line bg-surface">
            <button
              type="button"
              className="px-2.5 py-1.5 text-teal hover:bg-teal-soft disabled:opacity-40"
              disabled={!canEditNights || stop.nights <= 0}
              onClick={() => onNightsChange?.(Math.max(0, stop.nights - 1))}
              aria-label={`Fewer nights in ${stop.city}`}
            >
              −
            </button>
            <span className="min-w-6 text-center text-sm font-semibold">
              {stop.nights}
            </span>
            <button
              type="button"
              className="px-2.5 py-1.5 text-teal hover:bg-teal-soft disabled:opacity-40"
              disabled={!canEditNights || atMax}
              onClick={() => onNightsChange?.(stop.nights + 1)}
              aria-label={`More nights in ${stop.city}`}
            >
              +
            </button>
          </div>
        </div>
        {onRemove && (
          <button
            type="button"
            className="text-xs font-semibold text-ink-muted transition hover:text-warn"
            onClick={onRemove}
            aria-label={`Remove ${stop.city} from route`}
          >
            Remove
          </button>
        )}
      </div>
    </li>
  );
}
