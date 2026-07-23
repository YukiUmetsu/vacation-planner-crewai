import { apiFetch } from "./http";
import type { UserProfile } from "../components/profile/ProfilePage";
import { clampEnergyLevel } from "../lib/energyLevel";

export type ApiVisitedPlace = {
  name: string;
  city?: string;
  note?: string;
};

export type ApiProfile = {
  user_id?: string;
  display_name: string;
  preferences: string;
  energy_level: number;
  interests: string[];
  visited_places: ApiVisitedPlace[];
  suggest_include_breakfast?: boolean;
  max_comfortable_minutes?: number;
  /** false when GET returns blank defaults (nothing saved server-side yet). */
  persisted?: boolean;
};

export function profileFromApi(api: ApiProfile): UserProfile {
  return {
    displayName: api.display_name || "",
    preferences: api.preferences || "",
    energyLevel: clampEnergyLevel(api.energy_level),
    interests: [...(api.interests || [])],
    visitedPlaces: (api.visited_places || []).map((p) => ({
      name: p.name,
      city: p.city || undefined,
      note: p.note || undefined,
    })),
    suggestIncludeBreakfast: Boolean(api.suggest_include_breakfast),
  };
}

export function profileToApi(profile: UserProfile): ApiProfile {
  return {
    display_name: profile.displayName,
    preferences: profile.preferences,
    energy_level: profile.energyLevel,
    interests: profile.interests,
    visited_places: profile.visitedPlaces.map((p) => ({
      name: p.name,
      city: p.city ?? "",
      note: p.note ?? "",
    })),
    suggest_include_breakfast: profile.suggestIncludeBreakfast,
  };
}

export async function getProfile(): Promise<{ profile: ApiProfile }> {
  return apiFetch<{ profile: ApiProfile }>("/profile", { method: "GET" });
}

export async function putProfile(
  profile: UserProfile,
): Promise<{ profile: ApiProfile }> {
  return apiFetch<{ profile: ApiProfile }>("/profile", {
    method: "PUT",
    body: JSON.stringify(profileToApi(profile)),
  });
}
