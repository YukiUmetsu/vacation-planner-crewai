import type { DayPlan, Place } from "../types/trip";
import { enrichPlace } from "./placeDetails";

export type DayTimeSummary = {
  activityMinutes: number;
  travelMinutes: number;
  totalMinutes: number;
  placesWithEstimate: number;
  placesTotal: number;
};

/** Demo transit legs between known Tokyo/Kyoto stops (minutes). */
const DEMO_TRAVEL_LEG: Record<string, number> = {
  "shibuya>harajuku": 18,
  "harajuku>yanaka": 40,
  "tsukiji>ameyoko": 28,
  "ameyoko>nakamise": 15,
  "shibuya>teamlab-planets": 45,
  "harajuku>teamlab-planets": 48,
  "yanaka>teamlab-planets": 35,
  "shibuya>shimokitazawa": 22,
  "harajuku>shimokitazawa": 25,
};

function legKey(fromKey: string, toKey: string): string {
  return `${fromKey}>${toKey}`;
}

export function travelMinutesBetween(
  from: Place | undefined,
  to: Place,
): number {
  if (!from) return 0;
  if (typeof to.travel_minutes_from_previous === "number") {
    return to.travel_minutes_from_previous;
  }
  const known = DEMO_TRAVEL_LEG[legKey(from.place_key, to.place_key)];
  if (typeof known === "number") return known;
  // Fallback when unknown: short urban hop so totals still show
  return 20;
}

export function summarizeDayTimes(day: DayPlan): DayTimeSummary {
  const places = day.places.map(enrichPlace);
  let activityMinutes = 0;
  let travelMinutes = 0;
  let placesWithEstimate = 0;

  places.forEach((place, index) => {
    if (typeof place.estimated_minutes === "number") {
      activityMinutes += place.estimated_minutes;
      placesWithEstimate += 1;
    } else {
      activityMinutes += 60; // default visit block
    }
    if (index > 0) {
      travelMinutes += travelMinutesBetween(places[index - 1], place);
    }
  });

  return {
    activityMinutes,
    travelMinutes,
    totalMinutes: activityMinutes + travelMinutes,
    placesWithEstimate,
    placesTotal: places.length,
  };
}

export function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}
