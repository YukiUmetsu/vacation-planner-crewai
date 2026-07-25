import { apiFetch, ApiError } from "./http";

export type ResolvePlacePhotoResult = {
  photo_url?: string | null;
  places_photo_name?: string | null;
  /** Preferred for `<img>` — avoids googleusercontent Referer 403s. */
  photo_data_url?: string | null;
};

/** Dedupe in-flight photo resolves (React Strict Mode double-mount). */
const inflight = new Map<string, Promise<ResolvePlacePhotoResult>>();

/** Session success cache — reopen panel without re-hitting the BFF. */
const SUCCESS_TTL_MS = 30 * 60 * 1000;
const successCache = new Map<
  string,
  { result: ResolvePlacePhotoResult; expiresAt: number }
>();

/** After 503 / rate-limit, cool down before another upstream attempt. */
const TRANSIENT_COOLDOWN_MS = 90 * 1000;
const cooldownUntil = new Map<string, number>();

function photoCacheKey(input: {
  tripId: string;
  placeKey?: string;
  photoName?: string;
  placeId?: string;
}): string {
  return [
    input.tripId.trim(),
    input.placeKey?.trim() || "",
    input.placeId?.trim() || "",
    input.photoName?.trim() || "",
  ].join("|");
}

function photoRequestKey(input: {
  tripId: string;
  placeKey?: string;
  photoName?: string;
  placeId?: string;
  refresh?: boolean;
}): string {
  return `${photoCacheKey(input)}|${input.refresh ? "1" : "0"}`;
}

/** Test helper — clear session photo caches. */
export function clearPlacePhotoClientCacheForTests(): void {
  inflight.clear();
  successCache.clear();
  cooldownUntil.clear();
}

/** Fresh Google Places / Wikipedia photo (auth + trip ownership; key on BFF). */
export function resolvePlacePhoto(input: {
  tripId: string;
  /** Prefer place_key — stable and short in the query string. */
  placeKey?: string;
  photoName?: string;
  placeId?: string;
  /** Bypass durable miss / stable URL cache (e.g. after img onError). */
  refresh?: boolean;
}): Promise<ResolvePlacePhotoResult> {
  const cacheKey = photoCacheKey(input);
  const requestKey = photoRequestKey(input);

  if (!input.refresh) {
    const hit = successCache.get(cacheKey);
    if (hit && hit.expiresAt > Date.now() && displayPhotoUrl(hit.result)) {
      return Promise.resolve(hit.result);
    }
    const cool = cooldownUntil.get(cacheKey) ?? 0;
    if (cool > Date.now()) {
      return Promise.reject(
        new ApiError(
          503,
          "Photo provider is temporarily unavailable; try again shortly",
          "photo_temporarily_unavailable",
        ),
      );
    }
  }

  const existing = inflight.get(requestKey);
  if (existing) return existing;

  const params = new URLSearchParams();
  params.set("trip_id", input.tripId.trim());
  if (input.placeKey?.trim()) {
    params.set("place_key", input.placeKey.trim());
  }
  // Prefer place_id over long photo resource names (query-string friendly).
  if (input.placeId?.trim()) {
    params.set("place_id", input.placeId.trim());
  } else if (input.photoName?.trim()) {
    params.set("photo_name", input.photoName.trim());
  }
  if (input.refresh) {
    params.set("refresh", "1");
  }
  const qs = params.toString();
  const pending = apiFetch<ResolvePlacePhotoResult>(`/places/photo?${qs}`)
    .then((result) => {
      if (displayPhotoUrl(result)) {
        successCache.set(cacheKey, {
          result,
          expiresAt: Date.now() + SUCCESS_TTL_MS,
        });
        cooldownUntil.delete(cacheKey);
      }
      return result;
    })
    .catch((err: unknown) => {
      if (
        err instanceof ApiError &&
        (err.status === 503 || err.code === "photo_temporarily_unavailable")
      ) {
        cooldownUntil.set(cacheKey, Date.now() + TRANSIENT_COOLDOWN_MS);
      }
      throw err;
    })
    .finally(() => {
      inflight.delete(requestKey);
    });
  inflight.set(requestKey, pending);
  return pending;
}

/** Best display URL from a resolve response (data URL first). */
export function displayPhotoUrl(
  result: ResolvePlacePhotoResult | null | undefined,
): string | null {
  const data = result?.photo_data_url?.trim();
  if (data?.startsWith("data:image/")) return data;
  const url = result?.photo_url?.trim();
  return url || null;
}
