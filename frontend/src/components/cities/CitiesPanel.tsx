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
import type { CityStop } from "../../types/trip";
import {
  canAddCityStop,
  maxCitiesForTrip,
  maxEditableNights,
  routeWindowIssue,
} from "../../lib/cityRoute";
import { cityImageUrl } from "../../lib/travelAtmosphere";
import { DragHandle } from "../DragHandle";
import { AddCityForm } from "./AddCityForm";
import { CityStopRow } from "./CityStopRow";
import { FeasibilityBanner } from "./FeasibilityBanner";
import { TravelPlanningLoading } from "./ProposeCitiesLoading";

type Props = {
  cities: CityStop[];
  dayCount?: number;
  destination?: string;
  feasibilityMessage?: string | null;
  checkingCity?: string | null;
  onPropose?: () => void;
  onConfirm?: () => void;
  onBackToDetails?: () => void;
  onNightsChange?: (index: number, nights: number) => void;
  onRemoveCity?: (index: number) => void;
  onAddCity?: (city: string, reason: string) => void;
  onSuggestCity?: (hint?: string) => void;
  suggestCityPending?: boolean;
  onMoveCity?: (fromIndex: number, toIndex: number) => void;
  onKeepFeasibility?: () => void;
  onUndoFeasibility?: () => void;
  proposePending?: boolean;
  confirmPending?: boolean;
};

function SortableCityItem({
  id,
  index,
  stop,
  destination,
  checkingCity,
  sortable,
  maxNights,
  nightsLocked,
  onNightsChange,
  onRemoveCity,
}: {
  id: string;
  index: number;
  stop: CityStop;
  destination: string;
  checkingCity?: string | null;
  sortable: boolean;
  maxNights?: number;
  nightsLocked: boolean;
  onNightsChange?: (index: number, nights: number) => void;
  onRemoveCity?: (index: number) => void;
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

  return (
    <li
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.85 : 1,
      }}
      className="list-none"
    >
      <CityStopRow
        stop={stop}
        imageUrl={cityImageUrl(stop.city, destination || stop.country)}
        checking={checkingCity === stop.city}
        maxNights={maxNights}
        nightsLocked={nightsLocked}
        leading={
          sortable ? (
            <DragHandle
              ref={setActivatorNodeRef}
              {...attributes}
              {...listeners}
              label={`Reorder ${stop.city}`}
            />
          ) : undefined
        }
        onNightsChange={
          onNightsChange ? (nights) => onNightsChange(index, nights) : undefined
        }
        onRemove={onRemoveCity ? () => onRemoveCity(index) : undefined}
      />
    </li>
  );
}

/**
 * Presentational Cities step chrome (mockup-aligned).
 * Parent owns draft route + mutations (see App live mode).
 */
export function CitiesPanel({
  cities,
  dayCount = 0,
  destination = "",
  feasibilityMessage,
  checkingCity,
  onPropose,
  onConfirm,
  onBackToDetails,
  onNightsChange,
  onRemoveCity,
  onAddCity,
  onSuggestCity,
  suggestCityPending,
  onMoveCity,
  onKeepFeasibility,
  onUndoFeasibility,
  proposePending,
  confirmPending,
}: Props) {
  const windowIssue = routeWindowIssue(cities, dayCount || null);
  const allowAdd = canAddCityStop(cities, dayCount || null);
  const cityCap = dayCount > 0 ? maxCitiesForTrip(dayCount) : 0;
  const canSort = Boolean(onMoveCity) && cities.length >= 2;

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const ids = cities.map(
    (stop, index) => stop.client_id || `${stop.city}-${index}`,
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id || !onMoveCity) return;
    const from = ids.indexOf(String(active.id));
    const to = ids.indexOf(String(over.id));
    if (from < 0 || to < 0 || from === to) return;
    onMoveCity(from, to);
  }

  if (proposePending) {
    return (
      <section className="overflow-hidden rounded-2xl border border-line/80 bg-surface/90 shadow-sm">
        {onBackToDetails && (
          <div className="border-b border-line/60 px-6 py-3 sm:px-8">
            <button
              type="button"
              onClick={onBackToDetails}
              className="text-sm font-semibold text-teal hover:underline"
            >
              ← Trip details
            </button>
          </div>
        )}
        <TravelPlanningLoading destination={destination} />
        <div className="border-t border-line/60 px-6 py-4 sm:px-8">
          <p className="text-sm text-ink-muted">
            This usually takes a minute — sit tight while we pace the overnights.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-line/80 bg-surface/90 p-6 shadow-sm sm:p-8">
      {onBackToDetails && (
        <button
          type="button"
          onClick={onBackToDetails}
          className="mb-4 text-sm font-semibold text-teal hover:underline"
        >
          ← Trip details
        </button>
      )}
      <h2 className="font-display text-2xl font-semibold text-ink">
        Add or edit your cities
      </h2>
      <p className="mt-1 text-sm text-ink-muted">
        Review your route, trim stops you don’t want, and adjust nights in each
        place. Drag the grip to reorder.
        {dayCount > 0 ? (
          <>
            {" "}
            Trip window: {dayCount} day{dayCount === 1 ? "" : "s"} (
            {Math.max(0, dayCount - 1)} overnight
            {dayCount === 2 ? "" : "s"}).
          </>
        ) : null}
      </p>

      {cities.length === 0 ? (
        <p className="mt-8 rounded-lg border border-dashed border-line bg-sand/40 px-4 py-8 text-center text-sm text-ink-muted">
          No cities yet — propose a route or add a stop below.
        </p>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext items={ids} strategy={verticalListSortingStrategy}>
            <ol className="mt-2">
              {cities.map((stop, index) => {
                const isLast = index === cities.length - 1;
                const maxNights =
                  dayCount > 0
                    ? maxEditableNights(cities, index, dayCount)
                    : undefined;
                const id = ids[index]!;
                return (
                  <SortableCityItem
                    key={id}
                    id={id}
                    index={index}
                    stop={stop}
                    destination={destination}
                    checkingCity={checkingCity}
                    sortable={canSort}
                    maxNights={maxNights}
                    nightsLocked={Boolean(dayCount > 0 && isLast)}
                    onNightsChange={onNightsChange}
                    onRemoveCity={onRemoveCity}
                  />
                );
              })}
            </ol>
          </SortableContext>
        </DndContext>
      )}

      <AddCityForm
        onAdd={allowAdd ? onAddCity : undefined}
        onSuggest={allowAdd ? onSuggestCity : undefined}
        suggestPending={suggestCityPending}
        disabledReason={
          !allowAdd && dayCount > 0
            ? `A ${dayCount}-day trip can include at most ${cityCap} ${
                cityCap === 1 ? "city" : "cities"
              }.`
            : undefined
        }
      />

      {windowIssue && cities.length > 0 && (
        <p className="mt-4 text-sm text-warn" role="status">
          {windowIssue}
        </p>
      )}

      {feasibilityMessage && (
        <FeasibilityBanner
          message={feasibilityMessage}
          onKeep={onKeepFeasibility}
          onUndo={onUndoFeasibility}
        />
      )}

      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <button
          type="button"
          className="flex-1 rounded-lg border border-teal bg-surface px-4 py-3 text-sm font-semibold text-teal hover:bg-teal-soft disabled:opacity-50"
          disabled={!onPropose || proposePending || confirmPending}
          onClick={onPropose}
        >
          {cities.length > 0 ? "Re-propose cities" : "Propose cities"}
        </button>
        <button
          type="button"
          className="flex-1 rounded-lg bg-teal px-4 py-3 text-sm font-semibold text-white hover:bg-teal-deep disabled:opacity-50"
          disabled={
            !onConfirm ||
            cities.length === 0 ||
            Boolean(windowIssue) ||
            confirmPending ||
            proposePending
          }
          onClick={onConfirm}
        >
          {confirmPending ? "Confirming…" : "Confirm route"}
        </button>
      </div>

      {!onPropose && !onConfirm && (
        <p className="mt-4 text-xs text-ink-muted">
          Propose and confirm handlers are not wired for this view.
        </p>
      )}
    </section>
  );
}
