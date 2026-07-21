import type { DayPlan, Place } from "../types/trip";

export function slugifyPlaceName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/** Ensure place_key is unique within a day's existing places. */
export function allocateUniquePlaceKey(
  baseName: string,
  existingKeys: Iterable<string>,
  orderFallback = 1,
): string {
  const taken = new Set(existingKeys);
  const base = slugifyPlaceName(baseName) || `place-${orderFallback}`;
  if (!taken.has(base)) return base;
  let n = 2;
  while (taken.has(`${base}-${n}`)) n += 1;
  return `${base}-${n}`;
}

/** Remove exactly one place by index; reindex order_in_day. */
export function removePlaceAt(day: DayPlan, placeIndex: number): DayPlan {
  if (placeIndex < 0 || placeIndex >= day.places.length) return day;
  const places = day.places
    .filter((_, i) => i !== placeIndex)
    .map((place, i) => ({ ...place, order_in_day: i + 1 }));
  return { ...day, places };
}

export function removePlaceFromDays(
  days: DayPlan[],
  dayIndex: number,
  placeIndex: number,
): DayPlan[] {
  return days.map((day) =>
    day.day_index !== dayIndex ? day : removePlaceAt(day, placeIndex),
  );
}

export function appendPlaceToDay(day: DayPlan, place: Place): DayPlan {
  const order = day.places.length + 1;
  const place_key = allocateUniquePlaceKey(
    place.place_key || place.name,
    day.places.map((p) => p.place_key),
    order,
  );
  return {
    ...day,
    places: [...day.places, { ...place, place_key, order_in_day: order }],
  };
}

export function appendPlaceToDays(
  days: DayPlan[],
  dayIndex: number,
  place: Place,
): DayPlan[] {
  return days.map((day) =>
    day.day_index !== dayIndex ? day : appendPlaceToDay(day, place),
  );
}
