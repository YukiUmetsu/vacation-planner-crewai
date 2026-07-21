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
  /** LEARNING: wire nights mutations / local draft state */
  onNightsChange?: (nights: number) => void;
};

const DEFAULT_HIGHLIGHTS: CityHighlightCategory[] = [
  { label: "Food", examples: "local markets, casual eats" },
  { label: "Culture", examples: "museums, historic sites" },
  { label: "Amusement", examples: "parks, nightlife" },
  { label: "Outdoors", examples: "walks, viewpoints" },
];

export function CityStopRow({
  stop,
  imageUrl,
  highlights = DEFAULT_HIGHLIGHTS,
  checking = false,
  onNightsChange,
}: Props) {
  const [open, setOpen] = useState(false);

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
            <CityPopularPopover city={stop.city} categories={highlights} />
          </div>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <p className="font-display text-lg font-semibold text-ink">{stop.city}</p>
        {stop.reason ? (
          <p className="mt-0.5 text-sm text-ink-muted">{stop.reason}</p>
        ) : null}
        {checking && (
          <p className="mt-1 text-xs text-ink-muted" role="status">
            Checking route…
          </p>
        )}
      </div>

      <div className="shrink-0 text-right">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Nights
        </p>
        <div className="mt-1 inline-flex items-center rounded-lg border border-line bg-surface">
          <button
            type="button"
            className="px-2.5 py-1.5 text-teal hover:bg-teal-soft disabled:opacity-40"
            disabled={!onNightsChange || stop.nights <= 0}
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
            disabled={!onNightsChange}
            onClick={() => onNightsChange?.(stop.nights + 1)}
            aria-label={`More nights in ${stop.city}`}
          >
            +
          </button>
        </div>
      </div>
    </li>
  );
}
