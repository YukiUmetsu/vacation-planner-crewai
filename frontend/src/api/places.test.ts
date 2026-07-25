import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./http";
import {
  clearPlacePhotoClientCacheForTests,
  resolvePlacePhoto,
} from "./places";

vi.mock("./http", async () => {
  const actual = await vi.importActual<typeof import("./http")>("./http");
  return {
    ...actual,
    apiFetch: vi.fn(),
  };
});

import { apiFetch } from "./http";

const apiFetchMock = vi.mocked(apiFetch);

describe("resolvePlacePhoto client cache", () => {
  afterEach(() => {
    clearPlacePhotoClientCacheForTests();
    apiFetchMock.mockReset();
  });

  it("reuses a successful resolve without calling the API again", async () => {
    apiFetchMock.mockResolvedValueOnce({
      photo_url: "https://upload.wikimedia.org/x.jpg",
      photo_data_url: "data:image/jpeg;base64,abc",
    });
    const input = { tripId: "t1", placeKey: "nijo" };
    const first = await resolvePlacePhoto(input);
    const second = await resolvePlacePhoto(input);
    expect(first.photo_data_url).toMatch(/^data:image\//);
    expect(second).toEqual(first);
    expect(apiFetchMock).toHaveBeenCalledTimes(1);
  });

  it("cools down after 503 so reopen does not re-hammer", async () => {
    apiFetchMock.mockRejectedValueOnce(
      new ApiError(503, "busy", "photo_temporarily_unavailable"),
    );
    const input = { tripId: "t1", placeKey: "kicc" };
    await expect(resolvePlacePhoto(input)).rejects.toMatchObject({
      status: 503,
    });
    await expect(resolvePlacePhoto(input)).rejects.toMatchObject({
      status: 503,
      code: "photo_temporarily_unavailable",
    });
    expect(apiFetchMock).toHaveBeenCalledTimes(1);
  });

  it("bypasses success cache when refresh=true", async () => {
    apiFetchMock
      .mockResolvedValueOnce({
        photo_data_url: "data:image/jpeg;base64,aaa",
      })
      .mockResolvedValueOnce({
        photo_data_url: "data:image/jpeg;base64,bbb",
      });
    const input = { tripId: "t1", placeKey: "nijo" };
    await resolvePlacePhoto(input);
    const refreshed = await resolvePlacePhoto({ ...input, refresh: true });
    expect(refreshed.photo_data_url).toContain("bbb");
    expect(apiFetchMock).toHaveBeenCalledTimes(2);
  });
});
