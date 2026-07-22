import { useState } from "react";
import type { EnergyLevel } from "../../lib/energyLevel";
import { EnergyLevelBars } from "./EnergyLevelBars";

export type UserProfile = {
  displayName: string;
  preferences: string;
  /** 1 = low energy / limited mobility, 5 = high capacity. */
  energyLevel: EnergyLevel;
  interests: string[];
  visitedPlaces: { name: string; city?: string; note?: string }[];
};

type Props = {
  profile: UserProfile;
  onChange: (next: UserProfile) => void;
  onBack?: () => void;
};

const INTEREST_OPTIONS = [
  "Food",
  "Culture",
  "Nature",
  "Amusement",
  "Trains",
  "Nightlife",
  "Shopping",
  "History",
];

const fieldClass =
  "mt-1.5 w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-sm text-ink outline-none focus:border-teal focus:ring-2 focus:ring-teal-soft";

/** Profile preferences + visited places (demo-local until Cognito/API). */
export function ProfilePage({ profile, onChange, onBack }: Props) {
  const [newInterest, setNewInterest] = useState("");
  const [newPlaceName, setNewPlaceName] = useState("");
  const [newPlaceCity, setNewPlaceCity] = useState("");

  function toggleInterest(label: string) {
    const has = profile.interests.includes(label);
    onChange({
      ...profile,
      interests: has
        ? profile.interests.filter((i) => i !== label)
        : [...profile.interests, label],
    });
  }

  function addCustomInterest() {
    const label = newInterest.trim();
    if (!label) return;
    const exists = profile.interests.some(
      (i) => i.toLowerCase() === label.toLowerCase(),
    );
    if (exists) {
      setNewInterest("");
      return;
    }
    onChange({
      ...profile,
      interests: [...profile.interests, label],
    });
    setNewInterest("");
  }

  function removeInterest(label: string) {
    onChange({
      ...profile,
      interests: profile.interests.filter((i) => i !== label),
    });
  }

  const customInterests = profile.interests.filter(
    (i) => !INTEREST_OPTIONS.includes(i),
  );

  function placeTagLabel(place: UserProfile["visitedPlaces"][number]): string {
    return place.city?.trim()
      ? `${place.name.trim()} · ${place.city.trim()}`
      : place.name.trim();
  }

  function addVisitedPlace() {
    const name = newPlaceName.trim();
    if (!name) return;
    const city = newPlaceCity.trim();
    const exists = profile.visitedPlaces.some(
      (p) =>
        p.name.toLowerCase() === name.toLowerCase() &&
        (p.city ?? "").toLowerCase() === city.toLowerCase(),
    );
    if (exists) {
      setNewPlaceName("");
      setNewPlaceCity("");
      return;
    }
    onChange({
      ...profile,
      visitedPlaces: [
        ...profile.visitedPlaces,
        { name, city: city || undefined },
      ],
    });
    setNewPlaceName("");
    setNewPlaceCity("");
  }

  function removeVisited(index: number) {
    onChange({
      ...profile,
      visitedPlaces: profile.visitedPlaces.filter((_, i) => i !== index),
    });
  }

  return (
    <section className="mx-auto max-w-2xl rounded-2xl border border-line/80 bg-surface/90 p-6 shadow-sm sm:p-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-2xl font-semibold text-ink">
            Your profile
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Preferences and places you’ve already been — used to personalize
            routes and day plans.
          </p>
        </div>
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="shrink-0 text-sm font-semibold text-teal hover:underline"
          >
            ← Back to trip
          </button>
        )}
      </div>

      <div className="mt-8 space-y-6">
        <label className="block text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Display name
          <input
            className={fieldClass}
            value={profile.displayName}
            onChange={(e) =>
              onChange({ ...profile, displayName: e.target.value })
            }
          />
        </label>

        <label className="block text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Travel preferences
          <textarea
            className={`${fieldClass} min-h-24 resize-y`}
            value={profile.preferences}
            onChange={(e) =>
              onChange({ ...profile, preferences: e.target.value })
            }
            placeholder="Pace, food style, must-avoids…"
          />
        </label>

        <fieldset>
          <legend className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            <span className="inline-flex items-center gap-1.5">
              Energy level
              <span className="group relative inline-flex normal-case">
                <button
                  type="button"
                  className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-line text-[10px] font-bold text-ink-muted hover:border-teal hover:text-teal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal"
                  aria-describedby="energy-level-help"
                  aria-label="About energy level"
                >
                  ?
                </button>
                <span
                  id="energy-level-help"
                  role="tooltip"
                  className="pointer-events-none absolute left-0 top-full z-20 mt-2 w-64 rounded-lg border border-line bg-surface px-3 py-2 text-left text-xs font-normal leading-snug text-ink opacity-0 shadow-md transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
                >
                  Like signal bars: 5 is high capacity, 1 is very low energy or
                  limited mobility. Day plans warn when total activity time looks
                  too heavy.
                </span>
              </span>
            </span>
          </legend>
          <div className="mt-3">
            <EnergyLevelBars
              value={profile.energyLevel}
              onChange={(energyLevel) => onChange({ ...profile, energyLevel })}
            />
          </div>
        </fieldset>

        <fieldset>
          <legend className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Areas of interest
          </legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {INTEREST_OPTIONS.map((label) => {
              const on = profile.interests.includes(label);
              return (
                <button
                  key={label}
                  type="button"
                  onClick={() => toggleInterest(label)}
                  className={`rounded-full border px-3 py-1.5 text-sm transition ${
                    on
                      ? "border-teal bg-teal-soft font-semibold text-teal-deep"
                      : "border-line bg-surface text-ink-muted hover:border-teal/40"
                  }`}
                >
                  {label}
                </button>
              );
            })}
            {customInterests.map((label) => (
              <button
                key={label}
                type="button"
                onClick={() => removeInterest(label)}
                className="inline-flex items-center gap-1.5 rounded-full border border-teal bg-teal-soft px-3 py-1.5 text-sm font-semibold text-teal-deep"
                title="Click to remove"
              >
                {label}
                <span aria-hidden className="text-ink-muted">
                  ×
                </span>
              </button>
            ))}
          </div>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="block min-w-0 flex-1 text-xs font-semibold text-ink-muted">
              Add a new interest
              <input
                className={fieldClass}
                value={newInterest}
                onChange={(e) => setNewInterest(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addCustomInterest();
                  }
                }}
                placeholder="e.g. Onsen, Photography, Anime"
              />
            </label>
            <button
              type="button"
              onClick={addCustomInterest}
              disabled={!newInterest.trim()}
              className="rounded-lg bg-teal px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-deep disabled:cursor-not-allowed disabled:opacity-50"
            >
              Add interest
            </button>
          </div>
        </fieldset>

        <fieldset>
          <legend className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Places I’ve been
          </legend>
          <p className="mt-1 text-xs text-ink-muted">
            Tags of spots to avoid repeating in day plans. Click a tag to remove.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {profile.visitedPlaces.map((place, index) => (
              <button
                key={`${place.name}-${place.city ?? ""}-${index}`}
                type="button"
                onClick={() => removeVisited(index)}
                className="inline-flex items-center gap-1.5 rounded-full border border-teal bg-teal-soft px-3 py-1.5 text-sm font-semibold text-teal-deep"
                title="Click to remove"
              >
                {placeTagLabel(place)}
                <span aria-hidden className="text-ink-muted">
                  ×
                </span>
              </button>
            ))}
            {profile.visitedPlaces.length === 0 && (
              <p className="text-sm text-ink-muted">No places yet.</p>
            )}
          </div>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="block min-w-0 flex-1 text-xs font-semibold text-ink-muted">
              Place
              <input
                className={fieldClass}
                value={newPlaceName}
                onChange={(e) => setNewPlaceName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addVisitedPlace();
                  }
                }}
                placeholder="e.g. Senso-ji"
              />
            </label>
            <label className="block min-w-0 flex-1 text-xs font-semibold text-ink-muted">
              City (optional)
              <input
                className={fieldClass}
                value={newPlaceCity}
                onChange={(e) => setNewPlaceCity(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addVisitedPlace();
                  }
                }}
                placeholder="e.g. Tokyo"
              />
            </label>
            <button
              type="button"
              onClick={addVisitedPlace}
              disabled={!newPlaceName.trim()}
              className="rounded-lg bg-teal px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-deep disabled:cursor-not-allowed disabled:opacity-50"
            >
              Add place
            </button>
          </div>
        </fieldset>

        <p className="text-xs text-ink-muted">
          Demo: changes stay in memory until refresh. Later: save via backend /
          Cognito user.
        </p>
      </div>
    </section>
  );
}
