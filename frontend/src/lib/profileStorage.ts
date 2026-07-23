import type { UserProfile } from "../components/profile/ProfilePage";
import { clampEnergyLevel } from "./energyLevel";
import { DEMO_PROFILE } from "../demo/profileDemo";

const STORAGE_KEY = "vacation-planner.profile.v1";

function isVisitedPlace(value: unknown): value is UserProfile["visitedPlaces"][number] {
  if (!value || typeof value !== "object") return false;
  const place = value as Record<string, unknown>;
  return typeof place.name === "string";
}

function blankProfile(): UserProfile {
  return {
    ...DEMO_PROFILE,
    interests: [...DEMO_PROFILE.interests],
    visitedPlaces: [],
  };
}

/** Parse stored JSON into a UserProfile; returns null if unusable. */
export function parseStoredProfile(raw: string): UserProfile | null {
  try {
    const data = JSON.parse(raw) as Record<string, unknown>;
    if (!data || typeof data !== "object") return null;
    const displayName =
      typeof data.displayName === "string" ? data.displayName : DEMO_PROFILE.displayName;
    const preferences =
      typeof data.preferences === "string" ? data.preferences : DEMO_PROFILE.preferences;
    const energyLevel = clampEnergyLevel(
      typeof data.energyLevel === "number" ? data.energyLevel : DEMO_PROFILE.energyLevel,
    );
    const interests = Array.isArray(data.interests)
      ? data.interests.filter((i): i is string => typeof i === "string")
      : [...DEMO_PROFILE.interests];
    const visitedPlaces = Array.isArray(data.visitedPlaces)
      ? data.visitedPlaces.filter(isVisitedPlace).map((p) => ({
          name: p.name,
          city: typeof p.city === "string" ? p.city : undefined,
          note: typeof p.note === "string" ? p.note : undefined,
        }))
      : [];

    return {
      displayName,
      preferences,
      energyLevel,
      interests,
      visitedPlaces,
      suggestIncludeBreakfast: data.suggestIncludeBreakfast === true,
    };
  } catch {
    return null;
  }
}

export function loadProfile(): UserProfile {
  if (typeof localStorage === "undefined") {
    return blankProfile();
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return blankProfile();
    }
    return parseStoredProfile(raw) ?? blankProfile();
  } catch {
    return blankProfile();
  }
}

export function saveProfile(profile: UserProfile): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
  } catch {
    // Quota / private mode — ignore.
  }
}

export const PROFILE_STORAGE_KEY = STORAGE_KEY;
