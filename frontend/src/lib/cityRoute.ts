import type { CityStop } from "../types/trip";

export type CityStopInput = {
  city: string;
  country?: string;
  nights?: number;
  reason?: string;
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

export function addCityStop(
  cities: CityStop[],
  input: CityStopInput,
  dayCount?: number | null,
): CityStop[] {
  const next: CityStop = {
    city: input.city,
    country: input.country,
    nights: input.nights ?? 1,
    arrival_day_index: 1,
    departure_day_index: 1,
    reason: input.reason,
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
  return recomputeCityDayRanges(
    cities.map((stop, i) =>
      i === index ? { ...stop, nights: Math.max(0, nights) } : stop,
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

export function overnightCityForDay(
  cities: CityStop[],
  dayIndex: number,
): string | undefined {
  return cities.find(
    (c) =>
      c.arrival_day_index <= dayIndex && c.departure_day_index >= dayIndex,
  )?.city;
}
