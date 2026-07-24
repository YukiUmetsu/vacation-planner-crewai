import { describe, expect, it } from "vitest";
import { displayPhotoUrl } from "../api/places";
import {
  canResolvePlacePhoto,
  isFreshPhotoMiss,
  isStablePhotoUrl,
  shouldSkipPlacePhotoResolve,
  storedPlacePhotoUrl,
} from "./placeImage";

describe("placeImage", () => {
  it("only short-circuits durable Wikimedia URLs", () => {
    expect(
      storedPlacePhotoUrl({
        photo_url: "https://upload.wikimedia.org/wikipedia/commons/a.jpg",
      }),
    ).toBe("https://upload.wikimedia.org/wikipedia/commons/a.jpg");
    expect(
      storedPlacePhotoUrl({
        photo_url: "https://lh3.googleusercontent.com/p.jpg",
      }),
    ).toBeNull();
    expect(storedPlacePhotoUrl({ photo_url: "  " })).toBeNull();
    expect(storedPlacePhotoUrl({})).toBeNull();
  });

  it("detects stable hosts", () => {
    expect(isStablePhotoUrl("https://upload.wikimedia.org/x.jpg")).toBe(true);
    expect(isStablePhotoUrl("https://lh3.googleusercontent.com/x")).toBe(false);
  });

  it("skips BFF for durable URL or fresh miss", () => {
    expect(
      shouldSkipPlacePhotoResolve({
        photo_url: "https://upload.wikimedia.org/x.jpg",
      }),
    ).toBe("use_url");
    expect(
      shouldSkipPlacePhotoResolve({
        photo_status: "none",
        photo_checked_at: new Date().toISOString(),
      }),
    ).toBe("miss");
    expect(
      shouldSkipPlacePhotoResolve({
        place_id: "ChIJ123",
      }),
    ).toBe("resolve");
  });

  it("treats recent photo_status none as a fresh miss", () => {
    expect(
      isFreshPhotoMiss({
        photo_status: "none",
        photo_checked_at: new Date().toISOString(),
      }),
    ).toBe(true);
    expect(isFreshPhotoMiss({ photo_status: "ok" })).toBe(false);
  });

  it("does not invent stock images when photo is missing", () => {
    expect(
      canResolvePlacePhoto({
        category: "food",
        name: "Ramen Shop",
        place_key: "ramen",
      } as never),
    ).toBe(false);
    expect(
      canResolvePlacePhoto({
        place_id: "ChIJ123",
      }),
    ).toBe(true);
  });

  it("prefers data URLs for display", () => {
    expect(
      displayPhotoUrl({
        photo_data_url: "data:image/jpeg;base64,abc",
        photo_url: "https://cdn.example/p.jpg",
      }),
    ).toBe("data:image/jpeg;base64,abc");
    expect(
      displayPhotoUrl({ photo_url: "https://cdn.example/p.jpg" }),
    ).toBe("https://cdn.example/p.jpg");
  });
});
