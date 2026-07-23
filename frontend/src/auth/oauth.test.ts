import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

describe("oauth URL builders", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_COGNITO_DOMAIN", "example.auth.us-east-1.amazoncognito.com");
    vi.stubEnv("VITE_COGNITO_CLIENT_ID", "client123");
    vi.stubEnv("VITE_COGNITO_REDIRECT_URI", "http://localhost:5173/callback");
    vi.stubEnv("VITE_COGNITO_IDENTITY_PROVIDERS", "COGNITO,Google,Facebook");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("adds identity_provider for social authorize", async () => {
    const { buildAuthorizeUrl } = await import("./oauth");
    const url = new URL(
      buildAuthorizeUrl("challenge", "state1", { identityProvider: "Facebook" }),
    );
    expect(url.pathname).toBe("/oauth2/authorize");
    expect(url.searchParams.get("identity_provider")).toBe("Facebook");
    expect(url.searchParams.get("code_challenge")).toBe("challenge");
    expect(url.searchParams.get("state")).toBe("state1");
  });

  it("builds Hosted UI signup URL", async () => {
    const { buildSignupUrl } = await import("./oauth");
    const url = new URL(buildSignupUrl("challenge", "state2"));
    expect(url.pathname).toBe("/signup");
    expect(url.searchParams.get("client_id")).toBe("client123");
    expect(url.searchParams.get("redirect_uri")).toBe(
      "http://localhost:5173/callback",
    );
  });
});

describe("config identity providers", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("defaults to COGNITO when providers env is empty", async () => {
    vi.stubEnv("VITE_COGNITO_DOMAIN", "example.auth.us-east-1.amazoncognito.com");
    vi.stubEnv("VITE_COGNITO_CLIENT_ID", "client123");
    vi.stubEnv("VITE_COGNITO_REDIRECT_URI", "http://localhost:5173/callback");
    vi.stubEnv("VITE_COGNITO_IDENTITY_PROVIDERS", "");
    const { getCognitoConfig, getSocialProviders } = await import("./config");
    expect(getCognitoConfig().identityProviders).toEqual(["COGNITO"]);
    expect(getSocialProviders()).toEqual([]);
  });

  it("parses social providers from env", async () => {
    vi.stubEnv("VITE_COGNITO_DOMAIN", "example.auth.us-east-1.amazoncognito.com");
    vi.stubEnv("VITE_COGNITO_CLIENT_ID", "client123");
    vi.stubEnv("VITE_COGNITO_REDIRECT_URI", "http://localhost:5173/callback");
    vi.stubEnv("VITE_COGNITO_IDENTITY_PROVIDERS", "COGNITO,Facebook");
    const { getSocialProviders, isEmailAuthEnabled } = await import("./config");
    expect(getSocialProviders()).toEqual(["Facebook"]);
    expect(isEmailAuthEnabled()).toBe(true);
  });
});
