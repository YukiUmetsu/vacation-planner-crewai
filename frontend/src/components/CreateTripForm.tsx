import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { createTrip, updateTrip } from "../api/trips";
import {
  withEndDateChange,
  withStartDateChange,
  inclusiveDayCount,
  maxEndDateForStart,
  MAX_TRIP_DAYS,
} from "../lib/tripDates";
import type { CreateTripInput, DestinationType } from "../types/trip";

type Props = {
  /** Prefill when editing an existing trip. */
  initialValues?: CreateTripInput;
  /** When set, save via PUT instead of create. */
  tripId?: string | null;
  /** Called after create; may hydrate + start propose. Awaited so the button stays disabled. */
  onCreated?: (tripId: string) => void | Promise<void>;
  /** Called after a successful date/details update. */
  onUpdated?: (tripId: string) => void | Promise<void>;
};

const defaultForm: CreateTripInput = {
  origin: "New York",
  destination: "Japan",
  destination_type: "country",
  start_date: "2026-08-01",
  end_date: "2026-08-07",
  preferences: "food",
};

const fieldClass =
  "mt-1.5 w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-ink outline-none transition focus:border-teal focus:ring-2 focus:ring-teal-soft";
const labelClass = "block text-xs font-semibold uppercase tracking-wide text-ink-muted";

export function CreateTripForm({
  initialValues,
  tripId,
  onCreated,
  onUpdated,
}: Props) {
  const editing = Boolean(tripId);
  const [form, setForm] = useState<CreateTripInput>(
    () => initialValues ?? defaultForm,
  );

  useEffect(() => {
    if (initialValues) setForm(initialValues);
  }, [initialValues]);

  const dayCount = inclusiveDayCount(form.start_date, form.end_date);
  const datesOk = dayCount >= 1 && dayCount <= MAX_TRIP_DAYS;

  const saveMutation = useMutation({
    // Keep isPending true through post-save hydrate/propose kickoff.
    mutationFn: async (input: CreateTripInput) => {
      if (editing && tripId) {
        const data = await updateTrip(tripId, input);
        await onUpdated?.(tripId);
        return data;
      }
      const data = await createTrip(input);
      await onCreated?.(data.trip.trip_id);
      return data;
    },
  });

  function updateField<K extends keyof CreateTripInput>(
    key: K,
    value: CreateTripInput[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (saveMutation.isPending || !datesOk) return;
        const clamped = withEndDateChange(form, form.end_date);
        saveMutation.mutate(clamped);
      }}
    >
      <div>
        <h2 className="font-display text-2xl font-semibold text-ink">
          {editing ? "Edit trip details" : "Let’s create your trip"}
        </h2>
        <p className="mt-1 text-sm text-ink-muted">
          {editing
            ? "Change dates or destination, then re-propose cities."
            : "Where, when, and how you like to travel."}
        </p>
      </div>

      <label className={labelClass}>
        Origin
        <input
          className={fieldClass}
          value={form.origin}
          onChange={(e) => updateField("origin", e.target.value)}
          placeholder="Where are you starting from?"
          required
        />
      </label>

      <label className={labelClass}>
        Destination
        <input
          className={fieldClass}
          value={form.destination}
          onChange={(e) => updateField("destination", e.target.value)}
          placeholder="Where are you going?"
          required
        />
      </label>

      <fieldset>
        <legend className={labelClass}>Type</legend>
        <div className="mt-1.5 grid grid-cols-3 gap-2">
          {(["city", "country", "region"] as DestinationType[]).map((t) => {
            const selected = form.destination_type === t;
            return (
              <button
                key={t}
                type="button"
                onClick={() => updateField("destination_type", t)}
                className={`rounded-lg border px-3 py-2.5 text-sm capitalize transition ${
                  selected
                    ? "border-teal bg-teal-soft font-semibold text-teal-deep"
                    : "border-line bg-surface text-ink-muted hover:border-teal/40"
                }`}
              >
                {t}
              </button>
            );
          })}
        </div>
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className={labelClass}>
          Start
          <input
            className={fieldClass}
            type="date"
            value={form.start_date}
            onChange={(e) =>
              setForm((prev) => withStartDateChange(prev, e.target.value))
            }
            required
          />
        </label>
        <label className={labelClass}>
          End
          <input
            className={fieldClass}
            type="date"
            value={form.end_date}
            min={form.start_date}
            max={maxEndDateForStart(form.start_date)}
            onChange={(e) =>
              setForm((prev) => withEndDateChange(prev, e.target.value))
            }
            required
          />
        </label>
      </div>
      <p className="text-sm text-ink-muted">
        {dayCount} inclusive day{dayCount === 1 ? "" : "s"} (max {MAX_TRIP_DAYS}
        ). Pick an end date at most {MAX_TRIP_DAYS - 1} days after start.
      </p>

      <label className={labelClass}>
        Preferences
        <textarea
          className={`${fieldClass} min-h-24 resize-y`}
          value={form.preferences ?? ""}
          onChange={(e) => updateField("preferences", e.target.value)}
          placeholder="Food, pace, must-sees…"
        />
      </label>

      <button
        type="submit"
        disabled={saveMutation.isPending || !datesOk}
        className="w-full rounded-lg bg-teal px-4 py-3 text-sm font-semibold text-white transition hover:bg-teal-deep disabled:cursor-not-allowed disabled:opacity-60"
      >
        {saveMutation.isPending
          ? editing
            ? "Saving…"
            : "Creating…"
          : editing
            ? "Save & re-propose cities"
            : "Create trip"}
      </button>

      {saveMutation.isError && (
        <p className="text-sm text-warn" role="alert">
          {editing ? "Save failed" : "Create failed"}:{" "}
          {(saveMutation.error as Error).message}
        </p>
      )}
    </form>
  );
}
