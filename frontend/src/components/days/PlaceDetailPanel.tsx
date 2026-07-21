import { useEffect, useRef } from "react";
import type { Place } from "../../types/trip";

type Props = {
  place: Place;
  previousPlaceName?: string | null;
  onClose: () => void;
};

function mapsHref(place: Place): string {
  if (place.map_url) return place.map_url;
  const q = encodeURIComponent(
    place.map_embed_query ||
      [place.name, place.address].filter(Boolean).join(", "),
  );
  return `https://www.google.com/maps/search/?api=1&query=${q}`;
}

function mapsEmbedSrc(place: Place): string {
  const q = encodeURIComponent(
    place.map_embed_query ||
      [place.name, place.address].filter(Boolean).join(", "),
  );
  return `https://maps.google.com/maps?q=${q}&z=15&output=embed`;
}

/** Side panel / sheet with cost, hours, map, caveats. */
export function PlaceDetailPanel({
  place,
  previousPlaceName,
  onClose,
}: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus?.();
    };
  }, []);

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-ink/30 p-3 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="place-detail-title"
      onClick={onClose}
    >
      <aside
        className="flex h-full w-full max-w-md flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              {place.category || "Place"}
            </p>
            <h2
              id="place-detail-title"
              className="font-display text-2xl font-semibold text-ink"
            >
              {place.name}
            </h2>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="rounded-lg border border-line px-2.5 py-1 text-sm font-semibold text-ink-muted hover:bg-sand"
          >
            Close
          </button>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
          <dl className="grid grid-cols-1 gap-3 text-sm">
            <DetailRow label="Address" value={place.address || "—"} />
            <DetailRow label="Cost" value={place.cost || "—"} />
            <DetailRow
              label="Open / close"
              value={place.open_hours || "Hours not listed"}
            />
            <DetailRow
              label="Time needed"
              value={
                place.estimated_minutes
                  ? `~${place.estimated_minutes} min`
                  : "—"
              }
            />
            <DetailRow
              label="Main attraction"
              value={place.main_attraction || place.details || "—"}
            />
          </dl>

          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Why suggested
            </h3>
            <p className="mt-1.5 text-sm leading-relaxed text-ink">
              {place.why_suggested ||
                place.reason_to_visit ||
                "No suggestion reason yet."}
            </p>
          </section>

          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Watch out for
            </h3>
            {place.watch_outs && place.watch_outs.length > 0 ? (
              <ul className="mt-2 space-y-2">
                {place.watch_outs.map((w) => (
                  <li
                    key={w.label}
                    className="rounded-lg border border-sand-deep bg-warn-soft/50 px-3 py-2 text-sm"
                  >
                    <p className="font-semibold text-warn">{w.label}</p>
                    <p className="mt-0.5 text-ink-muted">{w.detail}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1.5 text-sm text-ink-muted">No caveats listed.</p>
            )}
            {previousPlaceName && (
              <p className="mt-2 text-xs text-ink-muted">
                Previous stop in this day:{" "}
                <span className="font-semibold text-ink">{previousPlaceName}</span>
              </p>
            )}
          </section>

          <section>
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                Map
              </h3>
              <a
                href={mapsHref(place)}
                target="_blank"
                rel="noreferrer"
                className="text-xs font-semibold text-teal hover:underline"
              >
                Open in Maps →
              </a>
            </div>
            <div className="overflow-hidden rounded-xl border border-line bg-sand/40">
              <iframe
                title={`Map of ${place.name}`}
                src={mapsEmbedSrc(place)}
                className="h-48 w-full border-0"
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
              />
            </div>
          </section>
        </div>
      </aside>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-b border-line/70 pb-2">
      <dt className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
        {label}
      </dt>
      <dd className="mt-0.5 text-ink">{value}</dd>
    </div>
  );
}
