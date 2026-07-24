import { useEffect, useRef, useState } from "react";
import { displayPhotoUrl, resolvePlacePhoto } from "../../api/places";
import { parseOpenHours } from "../../lib/openHours";
import {
  anyStoredPhotoUrl,
  canResolvePlacePhoto,
  shouldSkipPlacePhotoResolve,
  storedPlacePhotoUrl,
} from "../../lib/placeImage";
import type { Place } from "../../types/trip";

type Props = {
  place: Place;
  /** Required to refresh Places CDN URLs via the owned-trip photo proxy. */
  tripId?: string | null;
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
  tripId,
  previousPlaceName,
  onClose,
}: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const [imageUrl, setImageUrl] = useState<string | null>(() =>
    storedPlacePhotoUrl(place),
  );
  const [imageFailed, setImageFailed] = useState(false);
  const [photoLoading, setPhotoLoading] = useState(false);
  const [forceRefresh, setForceRefresh] = useState(false);
  /** One refresh attempt per panel open (avoid onError loops). */
  const didRefreshRef = useRef(false);
  const hoursRows = parseOpenHours(place.open_hours);
  const showPhoto = Boolean(imageUrl && !imageFailed);

  useEffect(() => {
    didRefreshRef.current = false;
    setForceRefresh(false);
  }, [place.place_key, tripId]);

  useEffect(() => {
    let cancelled = false;
    setImageFailed(false);

    const photoName = place.places_photo_name?.trim();
    const placeId = place.place_id?.trim();
    const placeKey = place.place_key?.trim();
    const ownedTripId = tripId?.trim();
    const skip = forceRefresh
      ? "resolve"
      : shouldSkipPlacePhotoResolve(place);

    if (skip === "use_url") {
      setPhotoLoading(false);
      setImageUrl(storedPlacePhotoUrl(place));
      return;
    }
    if (skip === "miss") {
      setPhotoLoading(false);
      setImageUrl(null);
      return;
    }

    const canRefresh =
      Boolean(ownedTripId) && Boolean(placeKey || photoName || placeId);

    // Prefer BFF data URL for Google CDN (Referer 403). Stable Wikimedia skips above.
    if (!canRefresh) {
      setPhotoLoading(false);
      setImageUrl(anyStoredPhotoUrl(place));
      return;
    }

    setPhotoLoading(true);
    setImageUrl(null);
    void resolvePlacePhoto({
      tripId: ownedTripId!,
      placeKey: placeKey || undefined,
      placeId: placeId || undefined,
      photoName: photoName || undefined,
      refresh: forceRefresh,
    })
      .then((res) => {
        if (cancelled) return;
        const url = displayPhotoUrl(res) || anyStoredPhotoUrl(place);
        if (url) {
          setImageUrl(url);
          setImageFailed(false);
        }
      })
      .catch(() => {
        if (cancelled) return;
        const fallback = anyStoredPhotoUrl(place) || storedPlacePhotoUrl(place);
        if (fallback && !forceRefresh) {
          setImageUrl(fallback);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setPhotoLoading(false);
          if (forceRefresh) setForceRefresh(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    tripId,
    place.place_key,
    place.photo_url,
    place.places_photo_name,
    place.place_id,
    place.photo_status,
    place.photo_checked_at,
    forceRefresh,
  ]);

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
        <div className="relative h-44 shrink-0 overflow-hidden bg-gradient-to-br from-teal-soft via-sand to-sand-deep">
          {showPhoto ? (
            <img
              src={imageUrl!}
              alt=""
              className="h-full w-full object-cover"
              loading="lazy"
              // googleusercontent.com 403s when the page Referer is sent.
              referrerPolicy="no-referrer"
              onError={() => {
                setImageFailed(true);
                // Broken durable URL — one BFF re-resolve per place open.
                if (tripId?.trim() && !didRefreshRef.current) {
                  didRefreshRef.current = true;
                  setForceRefresh(true);
                }
              }}
            />
          ) : null}
          <div
            className={`absolute inset-0 ${
              showPhoto
                ? "bg-gradient-to-t from-ink/55 via-ink/10 to-transparent"
                : "bg-gradient-to-t from-ink/40 via-transparent to-transparent"
            }`}
          />
          {!showPhoto && !photoLoading && canResolvePlacePhoto(place) ? (
            <p className="absolute inset-x-0 top-4 px-5 text-xs text-ink-muted">
              Photo unavailable
            </p>
          ) : null}
          <header className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 px-5 pb-4 pt-10">
            <div>
              <p
                className={`text-xs font-semibold uppercase tracking-wide ${
                  showPhoto ? "text-white/80" : "text-ink-muted"
                }`}
              >
                {place.category || "Place"}
              </p>
              <h2
                id="place-detail-title"
                className={`font-display text-2xl font-semibold drop-shadow ${
                  showPhoto ? "text-white" : "text-ink"
                }`}
              >
                {place.name}
              </h2>
            </div>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              className={`rounded-lg border px-2.5 py-1 text-sm font-semibold backdrop-blur ${
                showPhoto
                  ? "border-white/40 bg-ink/40 text-white hover:bg-ink/55"
                  : "border-line bg-surface/80 text-ink hover:bg-teal-soft"
              }`}
            >
              Close
            </button>
          </header>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
          <dl className="grid grid-cols-1 gap-3 text-sm">
            <DetailRow label="Address" value={place.address || "—"} />
            <DetailRow label="Cost" value={place.cost || "Not listed"} />
            <div className="border-b border-line/70 pb-2">
              <dt className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                Open / close
              </dt>
              <dd className="mt-1.5">
                {hoursRows.length > 0 ? (
                  <ul className="divide-y divide-line/60 rounded-lg border border-line/80">
                    {hoursRows.map((row) => (
                      <li
                        key={`${row.day}-${row.hours}`}
                        className="flex items-baseline justify-between gap-3 px-3 py-1.5"
                      >
                        <span className="shrink-0 text-ink-muted">{row.day}</span>
                        <span className="text-right text-ink">{row.hours}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <span className="text-ink">Hours not listed</span>
                )}
              </dd>
            </div>
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
