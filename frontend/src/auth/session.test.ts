import { describe, expect, it } from "vitest";
import { clearTokens, getIdToken, isSignedIn, setTokens } from "./session";

describe("auth session", () => {
  it("returns id token when not expired", () => {
    clearTokens();
    setTokens({
      idToken: "id.jwt",
      accessToken: "access.jwt",
      expiresAt: Date.now() + 60_000,
    });
    expect(getIdToken()).toBe("id.jwt");
    expect(isSignedIn()).toBe(true);
    clearTokens();
  });

  it("hides expired id token", () => {
    clearTokens();
    setTokens({
      idToken: "id.jwt",
      accessToken: "access.jwt",
      expiresAt: Date.now() - 1_000,
    });
    expect(getIdToken()).toBeNull();
    clearTokens();
  });

  it("treats soft-expired session with refresh token as signed in", () => {
    clearTokens();
    setTokens({
      idToken: "id.jwt",
      accessToken: "access.jwt",
      refreshToken: "refresh.jwt",
      expiresAt: Date.now() - 1_000,
    });
    expect(getIdToken()).toBeNull();
    expect(isSignedIn()).toBe(true);
    clearTokens();
  });

  it("treats soft-expired session without refresh as signed out", () => {
    clearTokens();
    setTokens({
      idToken: "id.jwt",
      accessToken: "access.jwt",
      expiresAt: Date.now() - 1_000,
    });
    expect(isSignedIn()).toBe(false);
    clearTokens();
  });
});
