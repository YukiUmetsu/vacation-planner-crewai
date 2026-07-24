import { apiFetch } from "./http";

export type ResolvePlacePhotoResult = {
  photo_url?: string | null;
  places_photo_name?: string | null;
  /** Preferred for `<img>` — avoids googleusercontent Referer 403s. */
  photo_data_url?: string | null;
};

/** Dedupe in-flight photo resolves (React Strict Mode double-mount). */
const inflight = new Map<string, Promise<ResolvePlacePhotoResult>>();

function photoRequestKey(input: {
  tripId: string;
  placeKey?: string;
  photoName?: string;
  placeId?: string;
  refresh?: boolean;
}): string {
  return [
    input.tripId.trim(),
    input.placeKey?.trim() || "",
    input.placeId?.trim() || "",
    input.photoName?.trim() || "",
    input.refresh ? "1" : "0",
  ].join("|");
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
  const key = photoRequestKey(input);
  const existing = inflight.get(key);
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
  const pending = apiFetch<ResolvePlacePhotoResult>(`/places/photo?${qs}`).finally(
    () => {
      inflight.delete(key);
    },
  );
  inflight.set(key, pending);
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
