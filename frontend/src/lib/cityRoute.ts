import type { CityStop } from "../types/trip";

export type CityStopInput = {
  city: string;
  country?: string;
  nights?: number;
  reason?: string;
  client_id?: string;
};

/** Sequential night coverage → arrival/departure day indexes (1-based). */
export function recomputeCityDayRanges(cities: CityStop[]): CityStop[] {
  let cursor = 1;
  return cities.map((stop) => {
    const nights = Math.max(0, stop.nights);
    const arrival_day_index = cursor;
    const departure_day_index = nights === 0 ? cursor : cursor + nights - 1;
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
  return recomputeCityDayRanges([...cities, next]);
}

export function setCityNights(
  cities: CityStop[],
  index: number,
  nights: number,
): CityStop[] {
  if (index < 0 || index >= cities.length) return cities;
  return recomputeCityDayRanges(
    cities.map((stop, i) =>
      i === index ? { ...stop, nights: Math.max(0, nights) } : stop,
    ),
  );
}

export function removeCityByClientId(
  cities: CityStop[],
  clientId: string | null | undefined,
): CityStop[] {
  if (!clientId) return cities;
  return recomputeCityDayRanges(
    cities.filter((stop) => stop.client_id !== clientId),
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
