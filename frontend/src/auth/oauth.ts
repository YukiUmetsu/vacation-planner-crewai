/**
 * Cognito Hosted UI OAuth helpers (authorize URL, token exchange, login orchestration).
 */

import {
  getCognitoConfig,
  type CognitoIdentityProvider,
} from "./config";
import { createPkce } from "./pkce";
import {
  clearTokens,
  getIdToken,
  getRefreshToken,
  getTokens,
  savePkcePending,
  setTokens,
  takePkcePending,
  type AuthTokens,
} from "./session";

export type BeginLoginOptions = {
  /** When set, Hosted UI skips the provider picker and opens this IdP. */
  provider?: CognitoIdentityProvider;
  /** Email signup uses Hosted UI /signup; social uses authorize (first visit creates user). */
  mode?: "signin" | "signup";
};

function randomState(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function mapTokenResponse(data: {
  id_token: string;
  access_token: string;
  refresh_token?: string;
  expires_in: number;
}): AuthTokens {
  return {
    idToken: data.id_token,
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    expiresAt: Date.now() + data.expires_in * 1000,
  };
}

function oauthQueryParams(
  challenge: string,
  state: string,
): Record<string, string> {
  const cfg = getCognitoConfig();
  return {
    client_id: cfg.clientId,
    response_type: "code",
    scope: cfg.scopes,
    redirect_uri: cfg.redirectUri,
    state,
    code_challenge_method: "S256",
    code_challenge: challenge,
  };
}

/** Hosted UI /oauth2/authorize URL with PKCE challenge. */
export function buildAuthorizeUrl(
  challenge: string,
  state: string,
  options?: { identityProvider?: CognitoIdentityProvider },
): string {
  const cfg = getCognitoConfig();
  const u = new URL(`https://${cfg.domain}/oauth2/authorize`);
  for (const [k, v] of Object.entries(oauthQueryParams(challenge, state))) {
    u.searchParams.set(k, v);
  }
  if (options?.identityProvider) {
    u.searchParams.set("identity_provider", options.identityProvider);
  }
  return u.toString();
}

/** Hosted UI email/password sign-up page with the same OAuth+PKCE params. */
export function buildSignupUrl(challenge: string, state: string): string {
  const cfg = getCognitoConfig();
  const u = new URL(`https://${cfg.domain}/signup`);
  for (const [k, v] of Object.entries(oauthQueryParams(challenge, state))) {
    u.searchParams.set(k, v);
  }
  return u.toString();
}

/** POST /oauth2/token — exchange authorization code + PKCE verifier for tokens. */
export async function exchangeAuthorizationCode(
  code: string,
  verifier: string,
): Promise<AuthTokens> {
  const cfg = getCognitoConfig();
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: cfg.clientId,
    code,
    redirect_uri: cfg.redirectUri,
    code_verifier: verifier,
  });

  const res = await fetch(`https://${cfg.domain}/oauth2/token`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`token exchange failed: ${res.status} ${text}`);
  }

  const data = (await res.json()) as {
    id_token: string;
    access_token: string;
    refresh_token?: string;
    expires_in: number;
  };
  return mapTokenResponse(data);
}

/** Optional: refresh id/access tokens with refresh_token grant. */
export async function refreshTokens(refreshToken: string): Promise<AuthTokens> {
  const cfg = getCognitoConfig();
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    client_id: cfg.clientId,
    refresh_token: refreshToken,
  });

  const res = await fetch(`https://${cfg.domain}/oauth2/token`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`token refresh failed: ${res.status} ${text}`);
  }

  const data = (await res.json()) as {
    id_token: string;
    access_token: string;
    refresh_token?: string;
    expires_in: number;
  };
  return mapTokenResponse({
    ...data,
    // Cognito often omits refresh_token on refresh; keep the old one.
    refresh_token: data.refresh_token ?? refreshToken,
  });
}

/** Start Hosted UI login (optional IdP + sign-in vs sign-up). */
export async function beginLogin(options?: BeginLoginOptions): Promise<void> {
  const { verifier, challenge } = await createPkce();
  const state = randomState();
  savePkcePending({ verifier, state });

  const provider = options?.provider;
  const mode = options?.mode ?? "signin";

  if (provider && provider !== "COGNITO") {
    window.location.assign(
      buildAuthorizeUrl(challenge, state, { identityProvider: provider }),
    );
    return;
  }

  if (mode === "signup") {
    window.location.assign(buildSignupUrl(challenge, state));
    return;
  }

  window.location.assign(
    buildAuthorizeUrl(
      challenge,
      state,
      provider === "COGNITO" ? { identityProvider: "COGNITO" } : undefined,
    ),
  );
}

/**
 * Handle /callback?code=&state= after Hosted UI redirect.
 * Returns true when tokens were stored.
 */
export async function completeLoginFromRedirect(
  search: string = window.location.search,
): Promise<boolean> {
  const params = new URLSearchParams(search);
  const code = params.get("code");
  const state = params.get("state");
  const err = params.get("error");
  if (err) {
    throw new Error(params.get("error_description") || err);
  }
  if (!code || !state) {
    return false;
  }

  const pending = takePkcePending();
  if (!pending || pending.state !== state) {
    throw new Error("OAuth state mismatch — try signing in again");
  }

  const tokens = await exchangeAuthorizationCode(code, pending.verifier);
  setTokens(tokens);
  return true;
}

/** Clear local session and optionally bounce through Cognito logout. */
export function logout(options?: { federated?: boolean }): void {
  clearTokens();
  if (!options?.federated) {
    window.location.assign("/");
    return;
  }
  try {
    const cfg = getCognitoConfig();
    const u = new URL(`https://${cfg.domain}/logout`);
    u.searchParams.set("client_id", cfg.clientId);
    u.searchParams.set("logout_uri", cfg.logoutUri);
    window.location.assign(u.toString());
  } catch {
    window.location.assign("/");
  }
}

/**
 * Return a usable id_token, refreshing with refresh_token when soft-expired.
 * On expiry with no refresh, or refresh failure, logs the user out (clears session + home).
 * API Gateway JWT authorizer returns 401 (never hits Lambda) without a valid Bearer token.
 */
export async function ensureIdToken(): Promise<string | null> {
  const current = getIdToken();
  if (current) return current;

  const stored = getTokens();
  if (!stored) {
    return null;
  }

  // Soft-expired (or missing id) while we still have a local session.
  const refresh = getRefreshToken();
  if (!refresh) {
    logout();
    return null;
  }

  try {
    const next = await refreshTokens(refresh);
    setTokens(next);
    return next.idToken;
  } catch {
    logout();
    return null;
  }
}
