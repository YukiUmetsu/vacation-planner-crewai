import { useState } from "react";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  type DragEndEvent,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { DayPlan, Place } from "../../types/trip";
import { enrichPlace } from "../../demo/placeDetails";
import {
  formatDuration,
  summarizeDayTimes,
} from "../../demo/dayTimes";
import {
  assessDayEnergyLoad,
  type EnergyLevel,
} from "../../lib/energyLevel";
import { TravelPlanningLoading } from "../cities/ProposeCitiesLoading";
import { DragHandle } from "../DragHandle";
import { AddPlaceForm, type PlaceDraft } from "./AddPlaceForm";
import { DayEnergyWarning } from "./DayEnergyWarning";
import { InlineDayPlanningCard } from "./InlineDayPlanningCard";
import { PlaceDetailPanel } from "./PlaceDetailPanel";

type Props = {
  days: DayPlan[];
  dayCount: number;
  /** Live trip id — used to refresh place photos via the owned-trip proxy. */
  tripId?: string | null;
  /** Trip destination — scenes/quotes while planning. */
  destination?: string;
  /** Overnight city for the day currently being planned. */
  planningCity?: string;
  /** Traveler energy from profile (1–5). */
  energyLevel?: EnergyLevel;
  onPlanNextDay?: () => void;
  pending?: boolean;
  complete?: boolean;
  suggestPendingDay?: number | null;
  onAddPlace?: (dayIndex: number, place: PlaceDraft) => void;
  onSuggestPlace?: (dayIndex: number, hint?: string) => void;
  /** Remove one place by day + index (not place_key — keys can collide). */
  onRemovePlace?: (dayIndex: number, placeIndex: number) => void;
  /** Reorder places within a day (draft + API). */
  onMovePlace?: (dayIndex: number, fromIndex: number, toIndex: number) => void;
  /** Remove an entire planned day. */
  onRemoveDay?: (dayIndex: number) => void;
};

/** Presentational Days timeline with per-day add / suggest + place detail. */
export function DaysPanel({
  days,
  dayCount,
  tripId,
  destination = "",
  planningCity,
  energyLevel = 3,
  onPlanNextDay,
  pending,
  complete,
  suggestPendingDay,
  onAddPlace,
  onSuggestPlace,
  onRemovePlace,
  onMovePlace,
  onRemoveDay,
}: Props) {
  const sorted = [...days].sort((a, b) => a.day_index - b.day_index);
  const [selected, setSelected] = useState<{
    dayIndex: number;
    placeIndex: number;
    place: Place;
    previousName: string | null;
    overnightCity: string;
  } | null>(null);

  function handleRemovePlace(dayIndex: number, placeIndex: number) {
    if (
      selected &&
      selected.dayIndex === dayIndex &&
      selected.placeIndex === placeIndex
    ) {
      setSelected(null);
    }
    onRemovePlace?.(dayIndex, placeIndex);
  }

  function handleRemoveDay(dayIndex: number) {
    if (selected?.dayIndex === dayIndex) {
      setSelected(null);
    }
    onRemoveDay?.(dayIndex);
  }

  if (pending && sorted.length === 0) {
    const city = (planningCity || destination).trim() || "your day";
    return (
      <section className="overflow-hidden rounded-2xl border border-line/80 bg-surface/90 shadow-sm">
        <TravelPlanningLoading
          destination={destination || city}
          place={planningCity || city}
          title={city}
          eyebrow="Planning your day"
        />
        <div className="border-t border-line/60 px-6 py-4 sm:px-8">
          <p className="text-sm text-ink-muted">
            This usually takes a minute — gathering places for {city}.
          </p>
        </div>
      </section>
    );
  }

  const nextDayIndex =
    sorted.reduce((max, d) => Math.max(max, d.day_index), 0) + 1;
  const nextCity = (planningCity || destination).trim() || "your next stop";

  return (
    <section className="rounded-2xl border border-line/80 bg-surface/90 p-6 shadow-sm sm:p-8">
      <h2 className="font-display text-2xl font-semibold text-ink">
        Plan your days
      </h2>
      <p className="mt-1 text-sm text-ink-muted">
        Build your itinerary one day at a time. Click a place for details — add
        or suggest more anytime.
      </p>

      <ol className="relative mt-8 space-y-8 border-l-2 border-teal-soft pl-6">
        {sorted.map((day) => (
          <DayBlock
            key={day.day_index}
            day={day}
            destination={destination}
            energyLevel={energyLevel}
            suggestPending={suggestPendingDay === day.day_index}
            dayPlanningPending={pending}
            onSelectPlace={(placeIndex, place, previousName) =>
              setSelected({
                dayIndex: day.day_index,
                placeIndex,
                place: enrichPlace(place),
                previousName,
                overnightCity: day.overnight_city,
              })
            }
            onAddPlace={
              onAddPlace
                ? (place) => onAddPlace(day.day_index, place)
                : undefined
            }
            onSuggestPlace={
              onSuggestPlace && day.places.length < 7
                ? (hint?: string) => onSuggestPlace(day.day_index, hint)
                : undefined
            }
            onRemovePlace={
              onRemovePlace
                ? (placeIndex) => handleRemovePlace(day.day_index, placeIndex)
                : undefined
            }
            onMovePlace={
              onMovePlace
                ? (from, to) => onMovePlace(day.day_index, from, to)
                : undefined
            }
            onRemoveDay={
              onRemoveDay ? () => handleRemoveDay(day.day_index) : undefined
            }
          />
        ))}
        {pending && sorted.length > 0 ? (
          <InlineDayPlanningCard
            dayIndex={nextDayIndex}
            city={nextCity}
            destination={destination}
          />
        ) : null}
      </ol>

      {!complete && (
        <button
          type="button"
          className="mt-8 rounded-lg bg-teal px-4 py-3 text-sm font-semibold text-white hover:bg-teal-deep disabled:opacity-50"
          disabled={!onPlanNextDay || pending}
          onClick={onPlanNextDay}
        >
          {pending ? "Planning next day…" : "Plan next day"}
        </button>
      )}

      {complete && (
        <p className="mt-8 text-sm font-semibold text-teal">
          All {dayCount} days planned.
        </p>
      )}

      {selected && (
        <PlaceDetailPanel
          place={selected.place}
          tripId={tripId}
          overnightCity={selected.overnightCity}
          destination={destination}
          previousPlaceName={selected.previousName}
          onClose={() => setSelected(null)}
        />
      )}
    </section>
  );
}

function DayBlock({
  day,
  destination,
  energyLevel,
  suggestPending,
  dayPlanningPending,
  onSelectPlace,
  onAddPlace,
  onSuggestPlace,
  onRemovePlace,
  onMovePlace,
  onRemoveDay,
}: {
  day: DayPlan;
  destination?: string;
  energyLevel: EnergyLevel;
  suggestPending?: boolean;
  dayPlanningPending?: boolean;
  onSelectPlace: (
    placeIndex: number,
    place: Place,
    previousName: string | null,
  ) => void;
  onAddPlace?: (place: PlaceDraft) => void;
  onSuggestPlace?: (hint?: string) => void;
  onRemovePlace?: (placeIndex: number) => void;
  onMovePlace?: (fromIndex: number, toIndex: number) => void;
  onRemoveDay?: () => void;
}) {
  const times = summarizeDayTimes(day);
  const energyLoad = assessDayEnergyLoad(energyLevel, times.totalMinutes);
  const canSort = Boolean(onMovePlace) && day.places.length >= 2;
  const ids = day.places.map(
    (p, index) => `${day.day_index}-${index}-${p.place_key}`,
  );
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id || !onMovePlace) return;
    const from = ids.indexOf(String(active.id));
    const to = ids.indexOf(String(over.id));
    if (from < 0 || to < 0 || from === to) return;
    onMovePlace(from, to);
  }

  return (
    <li className="relative">
      <span className="absolute -left-[1.9rem] flex h-7 w-7 items-center justify-center rounded-full bg-teal text-xs font-semibold text-white">
        {day.day_index}
      </span>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="font-display text-lg font-semibold text-ink">
            Day {day.day_index}: {day.theme || "Untitled"}
          </p>
          <p className="text-sm text-ink-muted">
            {day.date} · {day.overnight_city}
          </p>
        </div>
        <div className="flex flex-col items-start gap-2 sm:items-end">
          {day.places.length > 0 && (
            <p className="text-sm text-ink-muted sm:text-right">
              Min. total{" "}
              <span className="font-semibold text-teal">
                {formatDuration(times.totalMinutes)}
              </span>
              {times.travelMinutes > 0 && (
                <span className="text-ink-muted">
                  {" "}
                  (incl. {formatDuration(times.travelMinutes)} travel)
                </span>
              )}
            </p>
          )}
          {onRemoveDay && (
            <button
              type="button"
              aria-label={`Remove day ${day.day_index}`}
              className="text-xs font-semibold text-ink-muted hover:text-warn"
              onClick={() => {
                if (
                  window.confirm(
                    `Remove day ${day.day_index} (${day.theme || "Untitled"})? You can plan it again later.`,
                  )
                ) {
                  onRemoveDay();
                }
              }}
            >
              Remove day
            </button>
          )}
        </div>
      </div>

      {day.places.length > 0 && <DayEnergyWarning load={energyLoad} />}

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          <ul className="mt-3 space-y-2">
            {day.places.map((p: Place, index) => {
              const prev = index > 0 ? day.places[index - 1]?.name : null;
              const id = ids[index]!;
              return (
                <SortablePlaceRow
                  key={id}
                  id={id}
                  place={p}
                  sortable={canSort}
                  onSelect={() => onSelectPlace(index, p, prev ?? null)}
                  onRemove={
                    onRemovePlace ? () => onRemovePlace(index) : undefined
                  }
                />
              );
            })}
          </ul>
        </SortableContext>
      </DndContext>

      <AddPlaceForm
        city={day.overnight_city}
        destination={destination}
        onAdd={onAddPlace}
        onSuggest={onSuggestPlace}
        suggestPending={suggestPending}
        dayPlanningPending={dayPlanningPending}
      />
    </li>
  );
}

function SortablePlaceRow({
  id,
  place,
  sortable,
  onSelect,
  onRemove,
}: {
  id: string;
  place: Place;
  sortable: boolean;
  onSelect: () => void;
  onRemove?: () => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id, disabled: !sortable });
  const enriched = enrichPlace(place);

  return (
    <li
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.85 : 1,
      }}
      className="flex items-start justify-between gap-3 rounded-lg border border-line/70 bg-sand/30 px-3 py-2"
    >
      {sortable ? (
        <DragHandle
          ref={setActivatorNodeRef}
          {...attributes}
          {...listeners}
          label={`Reorder ${place.name}`}
          className="mt-0.5"
        />
      ) : null}
      <button
        type="button"
        aria-label={`View ${place.name}`}
        className="min-w-0 flex-1 text-left transition hover:opacity-80"
        onClick={onSelect}
      >
        <p className="text-sm font-semibold text-teal underline-offset-2 hover:underline">
          {place.name}
        </p>
        <p className="text-xs text-ink-muted">
          {[
            enriched.category,
            enriched.estimated_minutes
              ? `~${enriched.estimated_minutes} min`
              : null,
            enriched.reason_to_visit,
          ]
            .filter(Boolean)
            .join(" · ") || "Tap for details"}
        </p>
      </button>
      {onRemove && (
        <button
          type="button"
          aria-label={`Remove ${place.name}`}
          className="shrink-0 text-xs font-semibold text-ink-muted hover:text-warn"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
        >
          Remove
        </button>
      )}
    </li>
  );
}
