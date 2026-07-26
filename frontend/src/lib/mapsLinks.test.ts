import { describe, expect, it } from "vitest";
import {
  isMainlandChina,
  mapsEmbedSrc,
  mapsHref,
  usesAmapMaps,
} from "./mapsLinks";

describe("mapsLinks", () => {
  it("detects mainland China and SARs from trip geography", () => {
    expect(isMainlandChina("Shanghai")).toBe(true);
    expect(isMainlandChina("China")).toBe(true);
    expect(isMainlandChina("Hong Kong")).toBe(false);
    expect(isMainlandChina("Tokyo")).toBe(false);
  });

  it("uses Amap URIs for mainland overnight / destination", () => {
    const href = mapsHref(
      { name: "Yu Garden", lat: 31.227, lng: 121.492 },
      { overnightCity: "Shanghai", destination: "China" },
    );
    expect(href).toContain("uri.amap.com");
  });

  it("ignores stored Google maps_url for Amap places", () => {
    const href = mapsHref(
      {
        name: "Yu Garden",
        place_id: "amap:B000A8UIN8",
        places_provider: "amap",
        maps_url: "https://www.google.com/maps/search/?api=1&query=Yu+Garden",
      },
      { overnightCity: "Tokyo", destination: "Japan" },
    );
    expect(href).toContain("uri.amap.com");
    expect(href).toContain("poiid=B000A8UIN8");
    expect(href).not.toContain("google.com");
  });

  it("prefers poiid over coordinates when amap place_id is set", () => {
    const href = mapsHref(
      {
        name: "Spot",
        place_id: "amap:B000A7U3X0",
        lat: 31.2,
        lng: 121.5,
      },
      { overnightCity: "Shanghai", destination: "China" },
    );
    expect(href).toContain("poiid=B000A7U3X0");
  });

  it("returns null embed for mainland China (Amap URI not iframeable)", () => {
    expect(
      mapsEmbedSrc(
        { name: "Yu Garden", lat: 31.227, lng: 121.492 },
        { overnightCity: "Shanghai", destination: "China" },
      ),
    ).toBeNull();
  });

  it("uses Google embed for non-China places", () => {
    const embed = mapsEmbedSrc(
      { name: "Senso-ji", address: "Tokyo" },
      { overnightCity: "Tokyo", destination: "Japan" },
    );
    expect(embed).toContain("maps.google.com");
  });

  it("does not infer Amap from place name alone (e.g. restaurant abroad)", () => {
    expect(
      usesAmapMaps(
        {
          name: "Shanghai Dumpling House",
          address: "123 Main St, Chicago, IL",
        },
        { overnightCity: "Chicago", destination: "USA" },
      ),
    ).toBe(false);
    expect(
      mapsEmbedSrc(
        {
          name: "Shanghai Dumpling House",
          address: "123 Main St, Chicago, IL",
        },
        { overnightCity: "Chicago", destination: "USA" },
      ),
    ).toContain("maps.google.com");
  });

  it("honors places_provider and amap: place ids outside China context", () => {
    expect(
      usesAmapMaps(
        { name: "Any", places_provider: "amap" },
        { overnightCity: "Tokyo", destination: "Japan" },
      ),
    ).toBe(true);
    expect(
      usesAmapMaps(
        { name: "Any", place_id: "amap:B000A8UIN8" },
        { overnightCity: "Tokyo", destination: "Japan" },
      ),
    ).toBe(true);
  });
});
