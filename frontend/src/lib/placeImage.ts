import type { Place } from "../types/trip";

const STABLE_HOST_SUFFIXES = [
  "upload.wikimedia.org",
  "commons.wikimedia.org",
];

const MISS_TTL_MS = 7 * 24 * 60 * 60 * 1000;

/** True for Wikimedia (etc.) URLs safe to show without BFF proxying. */
export function isStablePhotoUrl(url: string | null | undefined): boolean {
  const raw = url?.trim() ?? "";
  if (!raw.startsWith("http")) return false;
  try {
    const host = new URL(raw).hostname.toLowerCase();
    return STABLE_HOST_SUFFIXES.some(
      (suffix) => host === suffix || host.endsWith(`.${suffix}`),
    );
  } catch {
    return false;
  }
}

/** Prefer a stable stored photo URL — never invent stock stand-ins. */
export function storedPlacePhotoUrl(
  place: Pick<Place, "photo_url">,
): string | null {
  const url = place.photo_url?.trim();
  if (!url) return null;
  // Only short-circuit on durable hosts; Google CDN links expire / 403 in <img>.
  return isStablePhotoUrl(url) ? url : null;
}

/** Any stored URL (including short-lived CDN) for fallback display after BFF. */
export function anyStoredPhotoUrl(
  place: Pick<Place, "photo_url">,
): string | null {
  const url = place.photo_url?.trim();
  return url || null;
}

export function isFreshPhotoMiss(
  place: Pick<Place, "photo_status" | "photo_checked_at">,
): boolean {
  if ((place.photo_status || "").trim().toLowerCase() !== "none") return false;
  const raw = place.photo_checked_at?.trim();
  if (!raw) return true;
  const checked = Date.parse(raw);
  if (Number.isNaN(checked)) return true;
  return Date.now() - checked < MISS_TTL_MS;
}

/**
 * Skip BFF when we already have a durable URL, or a fresh durable miss.
 * Still call BFF when only a Google place_id / photo name is present.
 */
export function shouldSkipPlacePhotoResolve(
  place: Pick<
    Place,
    "photo_url" | "photo_status" | "photo_checked_at" | "places_photo_name" | "place_id"
  >,
): "use_url" | "miss" | "resolve" {
  if (storedPlacePhotoUrl(place)) return "use_url";
  if (isFreshPhotoMiss(place)) return "miss";
  return "resolve";
}

export function canResolvePlacePhoto(
  place: Pick<Place, "places_photo_name" | "place_id" | "photo_url">,
): boolean {
  return Boolean(
    place.places_photo_name?.trim() ||
      place.place_id?.trim() ||
      place.photo_url?.trim(),
  );
}
