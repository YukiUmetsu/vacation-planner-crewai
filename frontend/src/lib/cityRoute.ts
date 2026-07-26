import type { CityStop } from "../types/trip";

export type CityStopInput = {
  city: string;
  country?: string;
  nights?: number;
  reason?: string;
  highlights?: string[];
  client_id?: string;
};

/**
 * Sequential night coverage → arrival/departure day indexes (1-based).
 *
 * When `dayCount` is set, the last stop is pinned to the trip window:
 * - `departure_day_index = dayCount`
 * - `nights = dayCount - arrival` so `sum(nights) === dayCount - 1`
 *   (matches backend synthetic routes + demo Osaka: nights 1 on days 6–7).
 */
export function recomputeCityDayRanges(
  cities: CityStop[],
  dayCount?: number | null,
): CityStop[] {
  if (cities.length === 0) return cities;

  const windowEnd =
    typeof dayCount === "number" && Number.isFinite(dayCount) && dayCount >= 1
      ? Math.floor(dayCount)
      : null;

  let cursor = 1;
  return cities.map((stop, index) => {
    const isLast = index === cities.length - 1;
    const arrival_day_index = cursor;
    let nights = Math.max(0, stop.nights);
    let departure_day_index =
      nights === 0 ? cursor : cursor + nights - 1;

    if (isLast && windowEnd != null && arrival_day_index <= windowEnd) {
      // Final travel day is covered without an extra overnight beyond dayCount - 1 total.
      departure_day_index = windowEnd;
      nights = windowEnd - arrival_day_index;
    }

    cursor = departure_day_index + 1;
    return {
      ...stop,
      nights,
      arrival_day_index,
      departure_day_index,
    };
  });
}

/** Expected overnight nights for a trip window (`day_count - 1`). */
export function expectedOvernightNights(dayCount: number): number {
  return Math.max(0, Math.floor(dayCount) - 1);
}

/**
 * Pace cap for overnight cities — mirrors backend ``max_cities_for_trip``.
 *
 * total_nights = day_count - 1:
 * - 1–3 nights → 1 city
 * - 4 nights → 2 cities
 * - 5–8 nights → 3 cities
 * - 9–13 nights → 4 cities
 * - 14+ nights → 5 cities
 */
export function maxCitiesForTrip(dayCount: number): number {
  const nights = Math.max(0, Math.floor(dayCount) - 1);
  if (nights <= 3) return 1;
  if (nights <= 4) return 2;
  if (nights <= 8) return 3;
  if (nights <= 13) return 4;
  return 5;
}

/**
 * Max nights the traveler can set on ``index`` without pushing later cities
 * past the trip window. Last stop is auto-pinned — returns its current nights.
 */
export function maxEditableNights(
  cities: CityStop[],
  index: number,
  dayCount: number,
): number {
  if (index < 0 || index >= cities.length || dayCount < 1) return 0;
  if (index === cities.length - 1) {
    return Math.max(0, cities[index]?.nights ?? 0);
  }
  const expected = expectedOvernightNights(dayCount);
  const otherNonLast = cities.reduce((sum, stop, i) => {
    if (i === index || i === cities.length - 1) return sum;
    return sum + Math.max(0, stop.nights);
  }, 0);
  return Math.max(0, expected - otherNonLast);
}

/** True when another overnight stop can be added under the trip pace cap. */
export function canAddCityStop(
  cities: CityStop[],
  dayCount: number | null | undefined,
): boolean {
  if (typeof dayCount !== "number" || dayCount < 1) return true;
  return cities.length < maxCitiesForTrip(dayCount);
}

/**
 * Human-readable reason the draft route would fail confirm, or null if OK.
 * Mirrors backend ``_assert_route_fits_window`` intent.
 */
export function routeWindowIssue(
  cities: CityStop[],
  dayCount: number | null | undefined,
): string | null {
  if (!cities.length) {
    return "Add or propose at least one city before confirming.";
  }
  if (typeof dayCount !== "number" || dayCount < 1) {
    return null;
  }
  const window = Math.floor(dayCount);
  const cityCap = maxCitiesForTrip(window);
  if (cities.length > cityCap) {
    const noun = cityCap === 1 ? "city" : "cities";
    return `A ${window}-day trip can include at most ${cityCap} ${noun}. Remove a stop.`;
  }

  const recomputed = recomputeCityDayRanges(cities, window);
  const nightsSum = recomputed.reduce((sum, c) => sum + c.nights, 0);
  const expected = expectedOvernightNights(window);
  if (nightsSum !== expected) {
    return (
      `This route has ${nightsSum} overnight night${nightsSum === 1 ? "" : "s"} ` +
      `but your trip needs ${expected} (days − 1). Adjust nights or remove a city.`
    );
  }

  const covered = new Set<number>();
  for (const stop of recomputed) {
    if (
      stop.arrival_day_index < 1 ||
      stop.departure_day_index > window ||
      stop.departure_day_index < stop.arrival_day_index
    ) {
      return `City days must stay within day 1–${window}. Reduce nights or remove a city.`;
    }
    for (let d = stop.arrival_day_index; d <= stop.departure_day_index; d++) {
      if (covered.has(d)) {
        return `Cities overlap on day ${d}. Adjust nights so each day has one overnight city.`;
      }
      covered.add(d);
    }
  }
  for (let d = 1; d <= window; d++) {
    if (!covered.has(d)) {
      return `Day ${d} is not covered. Add nights or another city so every trip day is included.`;
    }
  }
  return null;
}

export function addCityStop(
  cities: CityStop[],
  input: CityStopInput,
  dayCount?: number | null,
): CityStop[] {
  if (!canAddCityStop(cities, dayCount)) {
    return cities;
  }
  const next: CityStop = {
    city: input.city,
    country: input.country,
    nights: input.nights ?? 1,
    arrival_day_index: 1,
    departure_day_index: 1,
    reason: input.reason,
    highlights: input.highlights,
    client_id: input.client_id,
  };
  return recomputeCityDayRanges([...cities, next], dayCount);
}

export function setCityNights(
  cities: CityStop[],
  index: number,
  nights: number,
  dayCount?: number | null,
): CityStop[] {
  if (index < 0 || index >= cities.length) return cities;
  // Last stop nights are derived from the window — ignore manual edits.
  if (
    typeof dayCount === "number" &&
    dayCount >= 1 &&
    index === cities.length - 1
  ) {
    return recomputeCityDayRanges(cities, dayCount);
  }
  let nextNights = Math.max(0, nights);
  if (typeof dayCount === "number" && dayCount >= 1) {
    nextNights = Math.min(nextNights, maxEditableNights(cities, index, dayCount));
  }
  return recomputeCityDayRanges(
    cities.map((stop, i) =>
      i === index ? { ...stop, nights: nextNights } : stop,
    ),
    dayCount,
  );
}

export function removeCityByClientId(
  cities: CityStop[],
  clientId: string | null | undefined,
  dayCount?: number | null,
): CityStop[] {
  if (!clientId) return cities;
  return recomputeCityDayRanges(
    cities.filter((stop) => stop.client_id !== clientId),
    dayCount,
  );
}

export function removeCityAtIndex(
  cities: CityStop[],
  index: number,
  dayCount?: number | null,
): CityStop[] {
  if (index < 0 || index >= cities.length) return cities;
  return recomputeCityDayRanges(
    cities.filter((_, i) => i !== index),
    dayCount,
  );
}

/** Move a city stop within the draft route and recompute day windows. */
export function moveCityAtIndex(
  cities: CityStop[],
  fromIndex: number,
  toIndex: number,
  dayCount?: number | null,
): CityStop[] {
  if (
    fromIndex < 0 ||
    toIndex < 0 ||
    fromIndex >= cities.length ||
    toIndex >= cities.length ||
    fromIndex === toIndex
  ) {
    return cities;
  }
  const next = [...cities];
  const [moved] = next.splice(fromIndex, 1);
  if (!moved) return cities;
  next.splice(toIndex, 0, moved);
  return recomputeCityDayRanges(next, dayCount);
}

/** Case-insensitive duplicate check for draft inserts. */
export function cityAlreadyListed(
  cities: CityStop[],
  cityName: string,
): boolean {
  const key = cityName.trim().toLowerCase();
  if (!key) return false;
  return cities.some((c) => c.city.trim().toLowerCase() === key);
}

export function overnightCityForDay(
  cities: CityStop[],
  dayIndex: number,
): string | undefined {
  return cities.find(
    (c) =>
      c.arrival_day_index <= dayIndex && c.departure_day_index >= dayIndex,
  )?.city;
}
