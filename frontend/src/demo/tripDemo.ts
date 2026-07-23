import type { CityStop, DayPlan, TripBundle } from "../types/trip";

/** Static Japan trip so you can click through UI without the API. */
export const DEMO_TRIP_ID = "demo-trip-japan";

export const DEMO_CITIES: CityStop[] = [
  {
    city: "Tokyo",
    country: "Japan",
    nights: 3,
    arrival_day_index: 1,
    departure_day_index: 3,
    reason: "Neon neighborhoods, food, and easy day trips.",
  },
  {
    city: "Kyoto",
    country: "Japan",
    nights: 2,
    arrival_day_index: 4,
    departure_day_index: 5,
    reason: "Temples, gardens, and slower evenings.",
  },
  {
    city: "Osaka",
    country: "Japan",
    nights: 1,
    arrival_day_index: 6,
    departure_day_index: 7,
    reason: "Street food and a lively last night.",
  },
];

export const DEMO_DAYS: DayPlan[] = [
  {
    day_index: 1,
    date: "2026-08-01",
    theme: "Neighborhood walks",
    overnight_city: "Tokyo",
    places: [
      { name: "Shibuya", place_key: "shibuya" },
      { name: "Harajuku", place_key: "harajuku" },
      { name: "Yanaka", place_key: "yanaka" },
    ],
  },
  {
    day_index: 2,
    date: "2026-08-02",
    theme: "Food markets",
    overnight_city: "Tokyo",
    places: [
      { name: "Tsukiji Outer Market", place_key: "tsukiji" },
      { name: "Ameya-Yokocho", place_key: "ameyoko" },
      { name: "Nakamise Street", place_key: "nakamise" },
    ],
  },
];

export const DEMO_TRIP_BUNDLE: TripBundle = {
  trip: {
    trip_id: DEMO_TRIP_ID,
    origin: "New York",
    destination: "Japan",
    destination_type: "country",
    start_date: "2026-08-01",
    end_date: "2026-08-07",
    day_count: 7,
    preferences: "food",
    status: "routing_confirmed",
    next_day_index: 3,
  },
  route: {
    destination_type: "country",
    cities: DEMO_CITIES,
    rationale: "A classic east–west arc with short train hops.",
    total_nights: 6,
    status: "confirmed",
  },
  days: DEMO_DAYS,
};

/** Rough demo rule: Hiroshima after Kyoto looks tiring. */
export function demoFeasibilityMessage(
  cities: CityStop[],
): string | null {
  const names = cities.map((c) => c.city.toLowerCase());
  const hasHiroshima = names.includes("hiroshima");
  const hasKyoto = names.includes("kyoto");
  if (hasHiroshima && hasKyoto) {
    return "Kyoto → Hiroshima is a long day of travel and may make the plan feel rushed. Keep it only if that leg matters to you.";
  }
  return null;
}
