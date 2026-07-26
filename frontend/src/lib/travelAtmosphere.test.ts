import { describe, expect, it } from "vitest";
import {
  cityImageUrl,
  defaultTravelImageUrl,
  defaultTravelScenes,
  nextDefaultTravelImageUrl,
  pickQuestion,
  pickQuote,
  scenesForDestination,
  scenesForPlace,
  travelImageKey,
} from "./travelAtmosphere";

describe("travelAtmosphere", () => {
  it("returns Japan-specific scenes for Japan destinations", () => {
    const scenes = scenesForDestination("Japan");
    expect(scenes.length).toBeGreaterThan(1);
    expect(scenes[0]!.imageUrl).toContain("images.unsplash.com");
  });

  it("maps known cities to override thumbs", () => {
    expect(cityImageUrl("Tokyo")).toContain("photo-1540959733332");
    expect(cityImageUrl("Kyoto")).toContain("photo-1493976040374");
    expect(cityImageUrl("Shanghai")).toContain("photo-1548919973");
  });

  it("returns China scenes for Shanghai / China destinations", () => {
    const scenes = scenesForPlace("Shanghai", "China");
    expect(scenes[0]!.imageUrl).not.toContain("photo-1488646953014");
    expect(
      scenes.some(
        (s) =>
          s.caption.toLowerCase().includes("shanghai") ||
          s.caption.toLowerCase().includes("beijing") ||
          s.caption.toLowerCase().includes("west lake") ||
          s.caption.toLowerCase().includes("chengdu"),
      ),
    ).toBe(true);
    expect(scenesForDestination("China")[0]!.caption).not.toEqual(
      scenesForDestination("Atlantis")[0]!.caption,
    );
  });

  it("prefers city hero imagery when planning a known overnight", () => {
    const scenes = scenesForPlace("Tokyo", "Japan");
    expect(scenes[0]!.imageUrl).toContain("photo-1540959733332");
    expect(scenes[0]!.imageUrl).toContain("w=1600");
  });

  it("falls back to destination scenes for unknown cities", () => {
    const scenes = scenesForPlace("Obscureville", "France");
    expect(scenes.some((s) => s.caption.toLowerCase().includes("paris") || s.imageUrl.includes("photo-1502602898657"))).toBe(
      true,
    );
  });

  it("exposes default travel scenes for load-error fallbacks", () => {
    const defaults = defaultTravelScenes();
    expect(defaults.length).toBeGreaterThan(1);
    expect(defaultTravelImageUrl("Tokyo", 800)).toContain("w=800");
    expect(defaultTravelImageUrl("Tokyo")).not.toEqual(cityImageUrl("Tokyo"));
  });

  it("skips already-failed photos when picking the next default", () => {
    const first = defaultTravelScenes()[0]!.imageUrl;
    const next = nextDefaultTravelImageUrl([first], 800);
    expect(next).toBeTruthy();
    expect(travelImageKey(next!)).not.toEqual(travelImageKey(first));
    expect(next).toContain("w=800");
  });

  it("treats width variants of the same photo as the same failure", () => {
    const first = defaultTravelScenes()[0]!.imageUrl;
    const narrow = first.replace(/w=\d+/, "w=224");
    const next = nextDefaultTravelImageUrl([narrow], 800);
    expect(next).toBeTruthy();
    expect(travelImageKey(next!)).not.toEqual(travelImageKey(first));
  });

  it("does not use known-404 Unsplash photo ids", () => {
    const broken = [
      "photo-1501785888041-af3ef6d9e041",
      "photo-1528183429752-a53900bd20d8",
      "photo-1552832230-c0197dc311b5",
    ];
    const urls = [
      ...defaultTravelScenes().map((s) => s.imageUrl),
      cityImageUrl("Rome"),
      ...scenesForDestination("Thailand").map((s) => s.imageUrl),
    ];
    for (const url of urls) {
      for (const id of broken) {
        expect(url).not.toContain(id);
      }
    }
  });

  it("rotates quotes and questions by tick", () => {
    const a = pickQuote("Japan", 0);
    const b = pickQuote("Japan", 1);
    expect(a).not.toEqual(b);
    expect(pickQuestion("Japan", 0)).not.toEqual(pickQuestion("Japan", 1));
  });
});
