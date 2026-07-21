import type { Place } from "../types/trip";

/** Rich demo places keyed by place_key / name. */
export const DEMO_PLACE_DETAILS: Record<string, Place> = {
  shibuya: {
    name: "Shibuya",
    place_key: "shibuya",
    category: "other",
    address: "Shibuya Crossing, 2-chome, Shibuya City, Tokyo",
    cost: "Free (crossing / streets); cafés ¥800–¥1,500",
    open_hours: "Area open 24h; shops typically 10:00–21:00",
    estimated_minutes: 90,
    main_attraction: "Scramble crossing and people-watching from a café perch",
    reason_to_visit: "Iconic first evening energy",
    why_suggested:
      "Easy intro to Tokyo movement and a natural meet-up after arrival.",
    map_embed_query: "Shibuya Crossing Tokyo",
    watch_outs: [
      {
        label: "Crowds",
        detail: "Peak evenings are packed — keep valuables zipped.",
      },
      {
        label: "Distance to next",
        detail: "Harajuku is ~15–20 min walk or 1 metro stop; don’t overpack this block.",
      },
    ],
  },
  harajuku: {
    name: "Harajuku",
    place_key: "harajuku",
    category: "shopping",
    address: "Takeshita Street, Jingumae, Shibuya City, Tokyo",
    cost: "Free to wander; snacks ¥500–¥1,200",
    open_hours: "Takeshita shops ~11:00–20:00 (varies)",
    estimated_minutes: 75,
    main_attraction: "Takeshita Street + side alleys for crepes and thrift",
    reason_to_visit: "Youth culture stretch between Shibuya and Meiji",
    why_suggested: "Pairs well after Shibuya without a long transit hop.",
    map_embed_query: "Takeshita Street Harajuku Tokyo",
    watch_outs: [
      {
        label: "Closes early-ish",
        detail: "Many shops wind down by 20:00 — do this before late dinner.",
      },
      {
        label: "From Shibuya",
        detail: "Walk the Yamanote side streets or take JR 1 stop to avoid taxi wait.",
      },
    ],
  },
  yanaka: {
    name: "Yanaka",
    place_key: "yanaka",
    category: "culture",
    address: "Yanaka Ginza, Taito City, Tokyo",
    cost: "Free; snacks ¥300–¥800",
    open_hours: "Yanaka Ginza shops ~10:00–18:00",
    estimated_minutes: 120,
    main_attraction: "Old-town lanes and temple quiet vs central Tokyo",
    reason_to_visit: "Slower afternoon contrast",
    why_suggested: "Balances a neon-heavy day with a calmer neighborhood.",
    map_embed_query: "Yanaka Ginza Tokyo",
    watch_outs: [
      {
        label: "Travel time",
        detail: "From Harajuku expect ~35–45 min by metro — don’t sandwich it between two dense stops.",
      },
      {
        label: "Closing",
        detail: "Several shops close around 18:00; arrive mid-afternoon.",
      },
    ],
  },
  tsukiji: {
    name: "Tsukiji Outer Market",
    place_key: "tsukiji",
    category: "food",
    address: "4-chome, Tsukiji, Chuo City, Tokyo",
    cost: "Tasting crawl ¥2,000–¥4,000 pp",
    open_hours: "Most stalls 6:00–14:00; many closed Sun/Mon",
    estimated_minutes: 120,
    main_attraction: "Fresh seafood snacks and knife/tea specialty shops",
    reason_to_visit: "Morning food crawl",
    why_suggested: "Best early — matches a food-market day theme.",
    map_embed_query: "Tsukiji Outer Market Tokyo",
    watch_outs: [
      {
        label: "Closes early",
        detail: "Plan to finish by early afternoon; don’t save this for evening.",
      },
      {
        label: "Cash",
        detail: "Some stalls are cash-only.",
      },
    ],
  },
  ameyoko: {
    name: "Ameya-Yokocho",
    place_key: "ameyoko",
    category: "food",
    address: "Ueno, Taito City, Tokyo",
    cost: "Snacks ¥500–¥1,500; free to walk",
    open_hours: "Roughly 10:00–19:00",
    estimated_minutes: 60,
    main_attraction: "Busy market street under the train tracks",
    reason_to_visit: "Street food between Tsukiji and Asakusa",
    why_suggested: "Short hop from Ueno after a market morning.",
    map_embed_query: "Ameya-Yokocho Ueno Tokyo",
    watch_outs: [
      {
        label: "From Tsukiji",
        detail: "~25 min by metro — eat light at Tsukiji if you want more here.",
      },
    ],
  },
  nakamise: {
    name: "Nakamise Street",
    place_key: "nakamise",
    category: "culture",
    address: "Asakusa, Taito City, Tokyo",
    cost: "Free; souvenirs ¥500+",
    open_hours: "Shops ~9:00–18:00; temple grounds later",
    estimated_minutes: 60,
    main_attraction: "Approach to Senso-ji with classic snack stalls",
    reason_to_visit: "Temple approach + snacks",
    why_suggested: "Closes the food-market day near Ueno/Asakusa.",
    map_embed_query: "Nakamise-dori Asakusa Tokyo",
    watch_outs: [
      {
        label: "Already visited?",
        detail: "If Senso-ji is on your profile visited list, keep this short.",
      },
      {
        label: "Crowds",
        detail: "Late afternoon is busiest; go earlier if you dislike queues.",
      },
    ],
  },
  "teamlab-planets": {
    name: "teamLab Planets",
    place_key: "teamlab-planets",
    category: "amusement",
    address: "Toyosu, Koto City, Tokyo",
    cost: "Tickets ~¥3,800–¥4,200; book online",
    open_hours: "Typically 9:00–22:00 (entry slots)",
    estimated_minutes: 120,
    main_attraction: "Immersive digital art rooms (water + mirrors)",
    reason_to_visit: "Immersive art, book ahead",
    why_suggested:
      "Fits amusement interest and is a strong indoor option if weather turns.",
    map_embed_query: "teamLab Planets Tokyo",
    watch_outs: [
      {
        label: "Timed entry",
        detail: "Sold-out days are common — reserve before you lock the day.",
      },
      {
        label: "Far from central stops",
        detail: "From Shibuya/Harajuku expect ~40–50 min; don’t stack right after a distant stop.",
      },
      {
        label: "Clothing",
        detail: "Some rooms are wet — wear shorts you can roll up.",
      },
    ],
  },
  shimokitazawa: {
    name: "Shimokitazawa",
    place_key: "shimokitazawa",
    category: "other",
    address: "Kitazawa, Setagaya City, Tokyo",
    cost: "Free to wander; cafés ¥800–¥1,500",
    open_hours: "Cafés/shops ~11:00–21:00",
    estimated_minutes: 120,
    main_attraction: "Indie cafés, thrift, and small live houses",
    reason_to_visit: "Cafés and vinyl shops",
    why_suggested: "Relaxed counterpoint to tourist-heavy central wards.",
    map_embed_query: "Shimokitazawa Tokyo",
    watch_outs: [
      {
        label: "Transit",
        detail: "Odakyu / Keio Inokashira — plan the return before last trains.",
      },
    ],
  },
  "nishiki-market": {
    name: "Nishiki Market",
    place_key: "nishiki-market",
    category: "food",
    address: "Nishikikoji-dori, Nakagyo Ward, Kyoto",
    cost: "Tasting ¥1,500–¥3,000",
    open_hours: "Mostly 10:00–18:00; some stalls close earlier",
    estimated_minutes: 90,
    main_attraction: "Covered food street for Kyoto specialties",
    reason_to_visit: "Snack crawl mid-morning",
    why_suggested: "Classic Kyoto food intro before temples.",
    map_embed_query: "Nishiki Market Kyoto",
    watch_outs: [
      {
        label: "Closing",
        detail: "Do not leave this for late afternoon — stalls empty out.",
      },
    ],
  },
  "philosophers-path": {
    name: "Philosopher’s Path",
    place_key: "philosophers-path",
    category: "nature",
    address: "Sakyo Ward, Kyoto",
    cost: "Free",
    open_hours: "Path open; nearby temples have their own hours",
    estimated_minutes: 90,
    main_attraction: "Canal-side walk between temple pockets",
    reason_to_visit: "Quiet walk between temples",
    why_suggested: "Low-cost nature break after market crowds.",
    map_embed_query: "Philosopher's Path Kyoto",
    watch_outs: [
      {
        label: "Heat / rain",
        detail: "Little shade in summer; bring water or skip if storms.",
      },
    ],
  },
  dotonbori: {
    name: "Dotonbori",
    place_key: "dotonbori",
    category: "food",
    address: "Dotonbori, Chuo Ward, Osaka",
    cost: "Street eats ¥800–¥2,000",
    open_hours: "Food stalls late into the night",
    estimated_minutes: 90,
    main_attraction: "Neon canal food street",
    reason_to_visit: "Classic evening food street",
    why_suggested: "Natural Osaka finale for food-focused travelers.",
    map_embed_query: "Dotonbori Osaka",
    watch_outs: [
      {
        label: "Crowds",
        detail: "Weekend nights are shoulder-to-shoulder.",
      },
    ],
  },
};

export function enrichPlace(place: Place): Place {
  const fromKey = DEMO_PLACE_DETAILS[place.place_key];
  if (fromKey) {
    return { ...fromKey, ...place, ...fillMissing(place, fromKey) };
  }
  const fromName = Object.values(DEMO_PLACE_DETAILS).find(
    (p) => p.name.toLowerCase() === place.name.toLowerCase(),
  );
  if (fromName) {
    return {
      ...fromName,
      ...place,
      ...fillMissing(place, fromName),
      place_key: place.place_key,
    };
  }
  return place;
}

/** Prefer existing place fields; fill blanks from catalog. */
function fillMissing(place: Place, catalog: Place): Partial<Place> {
  return {
    address: place.address || catalog.address,
    cost: place.cost || catalog.cost,
    open_hours: place.open_hours || catalog.open_hours,
    main_attraction: place.main_attraction || catalog.main_attraction,
    why_suggested: place.why_suggested || catalog.why_suggested,
    watch_outs: place.watch_outs?.length ? place.watch_outs : catalog.watch_outs,
    map_embed_query: place.map_embed_query || catalog.map_embed_query,
    map_url: place.map_url || catalog.map_url,
    estimated_minutes: place.estimated_minutes ?? catalog.estimated_minutes,
    category: place.category || catalog.category,
    reason_to_visit: place.reason_to_visit || catalog.reason_to_visit,
  };
}

/** Full Place objects for suggest-a-place demo. */
export const DEMO_PLACE_SUGGESTIONS: Record<string, Place[]> = {
  Tokyo: [
    DEMO_PLACE_DETAILS["teamlab-planets"],
    DEMO_PLACE_DETAILS.shimokitazawa,
  ],
  Kyoto: [
    DEMO_PLACE_DETAILS["nishiki-market"],
    DEMO_PLACE_DETAILS["philosophers-path"],
  ],
  Osaka: [DEMO_PLACE_DETAILS.dotonbori],
};
