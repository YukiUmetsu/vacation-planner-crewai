/**
 * Curated travel imagery + copy for the propose-cities waiting experience.
 * Unsplash CDN URLs (no API key); city overrides for common destinations.
 */

export type TravelScene = {
  /** Unsplash CDN URL (w=1600). */
  imageUrl: string;
  /** Short credit label for accessibility / caption. */
  caption: string;
};

const U = (id: string, w = 1600) =>
  `https://images.unsplash.com/${id}?auto=format&fit=crop&w=${w}&q=80`;

/** Destination / region keyed scenes (lowercase substring match). */
const DESTINATION_SCENES: { match: RegExp; scenes: TravelScene[] }[] = [
  {
    match: /japan|tokyo|kyoto|osaka|okinawa|hokkaido/,
    scenes: [
      { imageUrl: U("photo-1540959733332-eab4deabeeaf"), caption: "Tokyo evening streets" },
      { imageUrl: U("photo-1493976040374-85c8e12f0c0e"), caption: "Kyoto temple path" },
      { imageUrl: U("photo-1528164344705-47542687000d"), caption: "Mount Fuji horizon" },
      { imageUrl: U("photo-1490806843957-31f4c9a91c65"), caption: "Japanese garden stillness" },
    ],
  },
  {
    match:
      /china|shanghai|beijing|hangzhou|chengdu|guangzhou|shenzhen|xi'?an|xian|nanjing|suzhou|chongqing|wuhan|中国|中國|北京|上海|杭州|成都|广州|廣州|深圳|西安|南京|苏州/,
    scenes: [
      { imageUrl: U("photo-1548919973-5cef591cdbc9"), caption: "Shanghai Bund skyline" },
      { imageUrl: U("photo-1508804185872-d7badad00f7d"), caption: "Beijing hutong light" },
      { imageUrl: U("photo-1599571234909-29ed5d1321d6"), caption: "West Lake calm" },
      { imageUrl: U("photo-1537531383198-c1fc642df4c8"), caption: "Chengdu street life" },
    ],
  },
  {
    match: /korea|seoul|busan|jeju|한국|서울/,
    scenes: [
      { imageUrl: U("photo-1538485399081-7191377e8241"), caption: "Seoul city pulse" },
      { imageUrl: U("photo-1517154421773-0529f29ea451"), caption: "Korean street night" },
    ],
  },
  {
    match: /italy|rome|florence|venice|milan|tuscany/,
    scenes: [
      { imageUrl: U("photo-1516483638261-f4dbaf036963"), caption: "Coastal Italy" },
      { imageUrl: U("photo-1529260830199-42c24126f198"), caption: "Roman evening light" },
      { imageUrl: U("photo-1534445867742-43195f401b6c"), caption: "Venice canals" },
    ],
  },
  {
    match: /france|paris|provence|lyon|nice/,
    scenes: [
      { imageUrl: U("photo-1502602898657-3e91760cbb34"), caption: "Paris rooftops" },
      { imageUrl: U("photo-1499856871958-5b9627545d1a"), caption: "Seine at dusk" },
      { imageUrl: U("photo-1520939817895-060bdaf4fe1b"), caption: "Provence light" },
    ],
  },
  {
    match: /spain|barcelona|madrid|seville|andalusia/,
    scenes: [
      { imageUrl: U("photo-1583422409516-2895a77efded"), caption: "Barcelona streets" },
      { imageUrl: U("photo-1558642452-9d2a7deb7f62"), caption: "Spanish plaza" },
    ],
  },
  {
    match: /greece|athens|santorini|crete|mykonos/,
    scenes: [
      { imageUrl: U("photo-1533105079780-92b9be482077"), caption: "Aegean blue" },
      { imageUrl: U("photo-1613395877344-13d4a8e0d49e"), caption: "Whitewashed cliffs" },
    ],
  },
  {
    match: /thailand|bangkok|chiang|phuket/,
    scenes: [
      // Replaces broken photo-1528183429752-a53900bd20d8 (404).
      { imageUrl: U("photo-1552465011-b4e21bf6e79a"), caption: "Thai temple gold" },
      { imageUrl: U("photo-1508009603885-50cf7c579365"), caption: "Bangkok canals" },
    ],
  },
];

const FALLBACK_SCENES: TravelScene[] = [
  { imageUrl: U("photo-1488646953014-85cb44e25828"), caption: "Open road travel" },
  { imageUrl: U("photo-1469474968028-56623f02e42e"), caption: "Mountain morning" },
  { imageUrl: U("photo-1476514525535-07fb3b4ae5f1"), caption: "Lake reflection" },
  { imageUrl: U("photo-1507525428034-b723cf961d3e"), caption: "Quiet shoreline" },
  { imageUrl: U("photo-1530789253388-582c481c54b0"), caption: "Market wander" },
  // Replaces broken alpine id photo-1501785888041-af3ef6d9e041 (404).
  { imageUrl: U("photo-1464822759023-fed622ff2c3b"), caption: "Mountain ridgeline" },
];

/** Generic travel scenes when city/destination imagery is missing or fails to load. */
export function defaultTravelScenes(): TravelScene[] {
  return FALLBACK_SCENES;
}

/** Well-known city → Unsplash thumb (w=224). */
const CITY_IMAGE_OVERRIDES: Record<string, string> = {
  tokyo: U("photo-1540959733332-eab4deabeeaf", 224),
  kyoto: U("photo-1493976040374-85c8e12f0c0e", 224),
  osaka: U("photo-1590559899731-a382839e5549", 224),
  hiroshima: U("photo-1528164344705-47542687000d", 224),
  nara: U("photo-1490806843957-31f4c9a91c65", 224),
  shanghai: U("photo-1548919973-5cef591cdbc9", 224),
  beijing: U("photo-1508804185872-d7badad00f7d", 224),
  hangzhou: U("photo-1599571234909-29ed5d1321d6", 224),
  chengdu: U("photo-1537531383198-c1fc642df4c8", 224),
  guangzhou: U("photo-1548919973-5cef591cdbc9", 224),
  shenzhen: U("photo-1548919973-5cef591cdbc9", 224),
  "xi'an": U("photo-1508804185872-d7badad00f7d", 224),
  xian: U("photo-1508804185872-d7badad00f7d", 224),
  nanjing: U("photo-1508804185872-d7badad00f7d", 224),
  suzhou: U("photo-1599571234909-29ed5d1321d6", 224),
  paris: U("photo-1502602898657-3e91760cbb34", 224),
  // Replaces broken photo-1552832230-c0197dc311b5 (404).
  rome: U("photo-1531572753322-ad063cecc140", 224),
  florence: U("photo-1523906834658-6e24ef2386f9", 224),
  venice: U("photo-1534445867742-43195f401b6c", 224),
  barcelona: U("photo-1583422409516-2895a77efded", 224),
  london: U("photo-1513635269975-59663e0ac1ad", 224),
  "new york": U("photo-1496442226666-8d4d0e62e6e9", 224),
  bangkok: U("photo-1508009603885-50cf7c579365", 224),
  singapore: U("photo-1525625293386-3f8f99389edd", 224),
  seoul: U("photo-1538485399081-7191377e8241", 224),
  busan: U("photo-1517154421773-0529f29ea451", 224),
  sydney: U("photo-1506973035872-a4ec16b8e8d9", 224),
  athens: U("photo-1555993539-1732b0258235", 224),
  santorini: U("photo-1613395877344-13d4a8e0d49e", 224),
};

export const TRAVEL_QUOTES: readonly string[] = [
  "The world is a book, and those who do not travel read only one page.",
  "Travel makes one modest. You see what a tiny place you occupy in the world.",
  "We travel not to escape life, but for life not to escape us.",
  "Jobs fill your pocket, but adventures fill your soul.",
  "To travel is to live.",
  "The journey not the arrival matters.",
  "Somewhere on the other side of this wait, a street you’ve never walked is waiting.",
  "Collect moments, not things — starting with the ones we sketch for you now.",
  "A good trip is paced like a good meal: room to taste, not rush.",
  "Maps are suggestions. Wonder is the real itinerary.",
];

export const TRAVEL_QUESTIONS: readonly string[] = [
  "Morning market or late-night noodles?",
  "Would you rather linger in one neighborhood or hop between views?",
  "Train window daydreams or walking until your feet complain (happily)?",
  "What would make this trip feel like “you” — not a checklist?",
  "Museum morning or hillside afternoon?",
  "If you could steal one golden hour anywhere here, where would it be?",
  "Are you packing for photos, flavors, or quiet corners?",
  "One perfect café stop: people-watching or notebook open?",
  "How adventurous do you want the first overnight to feel?",
  "What’s one thing you’d happily skip to sleep better?",
  "Sunrise hike or sunset rooftop?",
  "Local hole-in-the-wall or a reservation worth dressing up for?",
];

function hashSeed(text: string): number {
  let h = 0;
  for (let i = 0; i < text.length; i++) {
    h = (h * 31 + text.charCodeAt(i)) >>> 0;
  }
  return h;
}

/** Path-only key so w=/q= variants of the same Unsplash photo match. */
export function travelImageKey(url: string): string {
  try {
    return new URL(url).pathname;
  } catch {
    return url;
  }
}

/** Stable default image URL (thumb or hero via ``width``). */
export function defaultTravelImageUrl(seed = "travel", width = 224): string {
  const idx = hashSeed(seed.trim() || "travel") % FALLBACK_SCENES.length;
  return FALLBACK_SCENES[idx]!.imageUrl.replace(/w=\d+/, `w=${width}`);
}

/**
 * Next default travel image not already tried (by photo path).
 * Returns null only when every curated default was excluded.
 */
export function nextDefaultTravelImageUrl(
  exclude: Iterable<string> = [],
  width = 224,
): string | null {
  const banned = new Set(
    [...exclude].map((u) => travelImageKey(u)).filter(Boolean),
  );
  for (const scene of FALLBACK_SCENES) {
    if (banned.has(travelImageKey(scene.imageUrl))) continue;
    return scene.imageUrl.replace(/w=\d+/, `w=${width}`);
  }
  return null;
}

export function scenesForDestination(destination: string): TravelScene[] {
  const key = destination.trim().toLowerCase();
  if (!key) return FALLBACK_SCENES;
  for (const entry of DESTINATION_SCENES) {
    if (entry.match.test(key)) return entry.scenes;
  }
  return FALLBACK_SCENES;
}

/**
 * Prefer imagery for a specific city (or overnight), then fall back to the
 * trip destination pool so loading screens feel place-specific.
 */
export function scenesForPlace(
  place: string,
  destinationFallback?: string,
): TravelScene[] {
  const city = place.trim();
  const dest = (destinationFallback || "").trim();
  const cityKey = city.toLowerCase();

  const fromCity = city ? scenesForDestination(city) : [];
  const fromDest = dest ? scenesForDestination(dest) : [];

  // Prefer city/region-specific pools over generic fallbacks when both exist.
  const cityIsFallback =
    fromCity.length > 0 && fromCity[0] === FALLBACK_SCENES[0];
  const destIsFallback =
    fromDest.length > 0 && fromDest[0] === FALLBACK_SCENES[0];

  let pool: TravelScene[];
  if (fromCity.length && !cityIsFallback) pool = [...fromCity];
  else if (fromDest.length && !destIsFallback) pool = [...fromDest];
  else if (fromCity.length) pool = [...fromCity];
  else if (fromDest.length) pool = [...fromDest];
  else pool = [...FALLBACK_SCENES];

  // Lead with a known city hero when we have an override thumb.
  if (cityKey && CITY_IMAGE_OVERRIDES[cityKey]) {
    const hero: TravelScene = {
      imageUrl: CITY_IMAGE_OVERRIDES[cityKey]!.replace(/w=\d+/, "w=1600"),
      caption: `${city} streets`,
    };
    pool = [hero, ...pool.filter((s) => s.imageUrl !== hero.imageUrl)];
  }

  // Dedupe by URL while preserving order.
  const seen = new Set<string>();
  return pool.filter((s) => {
    if (seen.has(s.imageUrl)) return false;
    seen.add(s.imageUrl);
    return true;
  });
}

/** Stable thumb URL for a city name; falls back to destination pool. */
export function cityImageUrl(
  city: string,
  destinationFallback?: string,
): string {
  const key = city.trim().toLowerCase();
  if (key && CITY_IMAGE_OVERRIDES[key]) return CITY_IMAGE_OVERRIDES[key];
  const pool = scenesForPlace(city, destinationFallback);
  const idx = hashSeed(key || "city") % pool.length;
  return pool[idx]!.imageUrl.replace(/w=\d+/, "w=224");
}

export function pickQuote(seed: string, tick: number): string {
  const i = (hashSeed(seed) + tick) % TRAVEL_QUOTES.length;
  return TRAVEL_QUOTES[i]!;
}

export function pickQuestion(seed: string, tick: number): string {
  const i = (hashSeed(seed) + tick * 3) % TRAVEL_QUESTIONS.length;
  return TRAVEL_QUESTIONS[i]!;
}
