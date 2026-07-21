import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { createTrip } from "../api/trips";
import type { CreateTripInput, DestinationType } from "../types/trip";

type Props = {
  onCreated: (tripId: string) => void;
};

const initialForm: CreateTripInput = {
  origin: "New York",
  destination: "Japan",
  destination_type: "country",
  start_date: "2026-08-01",
  end_date: "2026-08-07",
  preferences: "food and trains",
};

const fieldClass =
  "mt-1.5 w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-ink outline-none transition focus:border-teal focus:ring-2 focus:ring-teal-soft";
const labelClass = "block text-xs font-semibold uppercase tracking-wide text-ink-muted";

export function CreateTripForm({ onCreated }: Props) {
  const [form, setForm] = useState<CreateTripInput>(initialForm);

  const createMutation = useMutation({
    mutationFn: createTrip,
    onSuccess: (data) => {
      onCreated(data.trip.trip_id);
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
        createMutation.mutate(form);
      }}
    >
      <div>
        <h2 className="font-display text-2xl font-semibold text-ink">
          Let’s create your trip
        </h2>
        <p className="mt-1 text-sm text-ink-muted">
          Where, when, and how you like to travel.
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
            onChange={(e) => updateField("start_date", e.target.value)}
            required
          />
        </label>
        <label className={labelClass}>
          End
          <input
            className={fieldClass}
            type="date"
            value={form.end_date}
            onChange={(e) => updateField("end_date", e.target.value)}
            required
          />
        </label>
      </div>

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
        disabled={createMutation.isPending}
        className="w-full rounded-lg bg-teal px-4 py-3 text-sm font-semibold text-white transition hover:bg-teal-deep disabled:cursor-not-allowed disabled:opacity-60"
      >
        {createMutation.isPending ? "Creating…" : "Create trip"}
      </button>

      {createMutation.isError && (
        <p className="text-sm text-warn" role="alert">
          Create failed: {(createMutation.error as Error).message}
        </p>
      )}
    </form>
  );
}
