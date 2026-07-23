import { describe, expect, it } from "vitest";
import {
  cityImageUrl,
  pickQuestion,
  pickQuote,
  scenesForDestination,
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
  });

  it("rotates quotes and questions by tick", () => {
    const a = pickQuote("Japan", 0);
    const b = pickQuote("Japan", 1);
    expect(a).not.toEqual(b);
    expect(pickQuestion("Japan", 0)).not.toEqual(pickQuestion("Japan", 1));
  });
});
