import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, getApiBaseUrl, shouldSendDevIdentity } from "./http";

describe("getApiBaseUrl", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("defaults to /api for Vite proxy", () => {
    vi.stubEnv("VITE_API_URL", "");
    expect(getApiBaseUrl()).toBe("/api");
  });

  it("uses VITE_API_URL without trailing slash", () => {
    vi.stubEnv("VITE_API_URL", "https://api.example.com/v1/");
    expect(getApiBaseUrl()).toBe("https://api.example.com/v1");
  });
});

describe("shouldSendDevIdentity", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("is true only in Vite DEV mode", () => {
    vi.stubEnv("DEV", true);
    expect(shouldSendDevIdentity()).toBe(true);
    vi.stubEnv("DEV", false);
    expect(shouldSendDevIdentity()).toBe(false);
  });
});

describe("apiFetch", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("calls /api path and includes dev identity in DEV", async () => {
    vi.stubEnv("DEV", true);
    vi.stubEnv("VITE_API_URL", "");
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );

    await apiFetch<{ ok: boolean }>("/trips");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/trips",
      expect.objectContaining({
        headers: expect.objectContaining({
          "content-type": "application/json",
          "x-dev-user-sub": "local-dev-user",
          "x-crew-mode": "fake",
        }),
      }),
    );
  });

  it("sends x-crew-mode agentcore when preferred in DEV", async () => {
    vi.stubEnv("DEV", true);
    vi.stubEnv("VITE_API_URL", "");
    localStorage.setItem("vp.devCrewMode", "agentcore");
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );

    await apiFetch("/trips");

    const [, init] = fetchMock.mock.calls[0]!;
    const headers = init?.headers as Record<string, string>;
    expect(headers["x-crew-mode"]).toBe("agentcore");
    localStorage.removeItem("vp.devCrewMode");
  });

  it("omits x-crew-mode when not in DEV", async () => {
    vi.stubEnv("DEV", false);
    vi.stubEnv("VITE_API_URL", "https://api.example.com");
    localStorage.setItem("vp.devCrewMode", "agentcore");
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );

    await apiFetch("/trips");

    const [, init] = fetchMock.mock.calls[0]!;
    const headers = init?.headers as Record<string, string>;
    expect(headers["x-crew-mode"]).toBeUndefined();
    localStorage.removeItem("vp.devCrewMode");
  });

  it("omits dev identity when not in DEV", async () => {
    vi.stubEnv("DEV", false);
    vi.stubEnv("VITE_API_URL", "https://api.example.com");
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );

    await apiFetch("/trips");

    const [, init] = fetchMock.mock.calls[0]!;
    const headers = init?.headers as Record<string, string>;
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.com/trips",
      expect.anything(),
    );
    expect(headers["x-dev-user-sub"]).toBeUndefined();
  });

  it("attaches Bearer id token when signed in", async () => {
    vi.stubEnv("DEV", true);
    vi.stubEnv("VITE_API_URL", "");
    const { setTokens, clearTokens } = await import("../auth/session");
    clearTokens();
    setTokens({
      idToken: "id.jwt.here",
      accessToken: "access",
      expiresAt: Date.now() + 60_000,
    });
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );

    await apiFetch("/trips");

    const [, init] = fetchMock.mock.calls[0]!;
    const headers = init?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer id.jwt.here");
    expect(headers["x-dev-user-sub"]).toBeUndefined();
    clearTokens();
  });

  it("throws ApiError with JSON error body", async () => {
    vi.stubEnv("DEV", true);
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: "Nope", code: "FORBIDDEN" }), {
        status: 403,
      }),
    );

    await expect(apiFetch("/trips")).rejects.toMatchObject({
      name: "ApiError",
      status: 403,
      message: "Nope (FORBIDDEN)",
      code: "FORBIDDEN",
    } satisfies Partial<ApiError>);
  });

  it("hides 5xx body detail from ApiError message", async () => {
    vi.stubEnv("DEV", true);
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          error: "Failed to log message: [Errno 2] No such file",
          code: "crew_failed",
        }),
        { status: 502 },
      ),
    );

    await expect(apiFetch("/trips/x/propose-cities")).rejects.toMatchObject({
      name: "ApiError",
      status: 502,
      message: "Something went wrong. Please try again.",
      code: "crew_failed",
    } satisfies Partial<ApiError>);
  });

  it("maps API Gateway 401 to a sign-in message", async () => {
    vi.stubEnv("DEV", true);
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ message: "Unauthorized" }), {
        status: 401,
      }),
    );

    await expect(apiFetch("/trips/x/propose-cities")).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      message: "Session expired or missing — sign in again.",
      code: "unauthorized",
    } satisfies Partial<ApiError>);
  });
});
