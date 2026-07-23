import { describe, expect, it, beforeEach, afterEach } from "vitest";
import {
  PROFILE_STORAGE_KEY,
  loadProfile,
  parseStoredProfile,
  saveProfile,
} from "./profileStorage";

describe("parseStoredProfile", () => {
  it("accepts a valid payload and clamps energy", () => {
    const profile = parseStoredProfile(
      JSON.stringify({
        displayName: "Ada",
        preferences: "trains",
        energyLevel: 9,
        interests: ["Food"],
        visitedPlaces: [{ name: "Senso-ji", city: "Tokyo" }],
      }),
    );
    expect(profile?.displayName).toBe("Ada");
    expect(profile?.energyLevel).toBe(5);
    expect(profile?.interests).toEqual(["Food"]);
    expect(profile?.suggestIncludeBreakfast).toBe(false);
  });

  it("returns null for garbage JSON", () => {
    expect(parseStoredProfile("{not-json")).toBeNull();
  });
});

describe("loadProfile / saveProfile", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("round-trips through localStorage", () => {
    saveProfile({
      displayName: "Sam",
      preferences: "slow",
      energyLevel: 2,
      interests: ["Nature"],
      visitedPlaces: [],
      suggestIncludeBreakfast: false,
    });
    const loaded = loadProfile();
    expect(loaded.displayName).toBe("Sam");
    expect(loaded.energyLevel).toBe(2);
    expect(loaded.suggestIncludeBreakfast).toBe(false);
    expect(localStorage.getItem(PROFILE_STORAGE_KEY)).toContain("Sam");
  });

  it("falls back to empty visited places for new users", () => {
    const loaded = loadProfile();
    expect(loaded.displayName).toBeTruthy();
    expect(loaded.energyLevel).toBeGreaterThanOrEqual(1);
    expect(loaded.visitedPlaces).toEqual([]);
  });
});
