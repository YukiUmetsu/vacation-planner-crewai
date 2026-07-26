/**
 * Map link helpers. Mainland China uses Amap; everyone else uses Google Maps.
 */

export function isMainlandChina(...texts: Array<string | null | undefined>): boolean {
  const blob = texts
    .map((t) => (t || "").trim())
    .filter(Boolean)
    .join(" ");
  if (!blob) return false;
  if (
    /hong\s*kong|\bhk\b|香港|macau|macao|澳門|澳门|taiwan|台灣|台湾|\btw\b/i.test(
      blob,
    )
  ) {
    return false;
  }
  if (
    /\bchina\b|\bprc\b|\bcn\b|中国|中國|内地|大陸|大陆|people'?s\s+republic\s+of\s+china/i.test(
      blob,
    )
  ) {
    return true;
  }
  return /beijing|shanghai|guangzhou|shenzhen|chengdu|hangzhou|chongqing|wuhan|xian|xi'?an|nanjing|suzhou|天津|北京|上海|广州|廣州|深圳|成都|杭州|重庆|重慶|西安|南京|苏州|蘇州/i.test(
    blob,
  );
}

type MapPlace = {
  name?: string | null;
  address?: string | null;
  place_id?: string | null;
  map_url?: string | null;
  maps_url?: string | null;
  map_embed_query?: string | null;
  lat?: number | null;
  lng?: number | null;
  places_provider?: string | null;
};

type MapContext = {
  overnightCity?: string;
  destination?: string;
};

function queryText(place: MapPlace): string {
  return (
    place.map_embed_query ||
    [place.name, place.address].filter(Boolean).join(", ")
  ).trim();
}

function isAmapPlaceId(placeId: string | null | undefined): boolean {
  return typeof placeId === "string" && placeId.trim().startsWith("amap:");
}

/** Strip `amap:` prefix for URI poiid. */
export function amapPoiId(placeId: string | null | undefined): string | null {
  const raw = (placeId || "").trim();
  if (!raw.toLowerCase().startsWith("amap:")) return null;
  const poi = raw.slice("amap:".length).trim();
  return poi || null;
}

export function isAmapWebUrl(url: string | null | undefined): boolean {
  const raw = (url || "").trim().toLowerCase();
  if (!raw) return false;
  try {
    const host = new URL(raw).hostname;
    return host === "uri.amap.com" || host === "www.amap.com" || host === "amap.com";
  } catch {
    return /(?:^|\/\/)(?:uri\.)?amap\.com\b/i.test(raw);
  }
}

/**
 * Prefer explicit enrich signals + trip geography — never infer from place name alone
 * (e.g. "Shanghai Dumpling House" in Chicago must stay on Google Maps).
 */
export function usesAmapMaps(
  place: MapPlace,
  ctx: MapContext = {},
): boolean {
  if (place.places_provider === "amap" || isAmapPlaceId(place.place_id)) {
    return true;
  }
  return isMainlandChina(ctx.overnightCity, ctx.destination);
}

/** Build an Amap URI: poiid → position → keyword search. */
export function buildAmapHref(
  place: MapPlace,
  ctx: MapContext = {},
): string {
  const name = encodeURIComponent(place.name?.trim() || "place");
  const poi = amapPoiId(place.place_id);
  if (poi) {
    return `https://uri.amap.com/marker?poiid=${encodeURIComponent(poi)}&name=${name}&src=vacation_planner&callnative=0`;
  }
  if (
    typeof place.lng === "number" &&
    typeof place.lat === "number" &&
    Number.isFinite(place.lng) &&
    Number.isFinite(place.lat)
  ) {
    return `https://uri.amap.com/marker?position=${place.lng},${place.lat}&name=${name}&coordinate=gaode&src=vacation_planner&callnative=0`;
  }
  const q = encodeURIComponent(queryText(place) || place.name || "");
  const city = encodeURIComponent((ctx.overnightCity || "").trim());
  const cityParam = city ? `&city=${city}` : "";
  return `https://uri.amap.com/search?keyword=${q}${cityParam}&src=vacation_planner&callnative=0`;
}

export function mapsHref(place: MapPlace, ctx: MapContext = {}): string {
  const overnightCity = ctx.overnightCity || "";
  const destination = ctx.destination || "";
  const amapCtx = { overnightCity, destination };
  const stored = (place.map_url || place.maps_url || "").trim();

  if (usesAmapMaps(place, amapCtx)) {
    // Crews often stash Google maps_url — ignore unless already an Amap URI.
    if (stored && isAmapWebUrl(stored)) return stored;
    return buildAmapHref(place, amapCtx);
  }

  if (stored) return stored;
  const q = encodeURIComponent(queryText(place));
  return `https://www.google.com/maps/search/?api=1&query=${q}`;
}

/**
 * Embeddable map URL, or null when the provider cannot be iframed (Amap URI).
 */
export function mapsEmbedSrc(
  place: MapPlace,
  ctx: MapContext = {},
): string | null {
  if (usesAmapMaps(place, ctx)) {
    // uri.amap.com sets X-Frame-Options; keep outbound link only.
    return null;
  }

  const q = encodeURIComponent(queryText(place));
  return `https://maps.google.com/maps?q=${q}&z=15&output=embed`;
}
