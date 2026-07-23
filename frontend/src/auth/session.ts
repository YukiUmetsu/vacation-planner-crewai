/** In-memory + sessionStorage token bag (MVP). No crypto learning required. */

export type AuthTokens = {
  idToken: string;
  accessToken: string;
  refreshToken?: string;
  /** Epoch ms when access/id tokens should be treated as expired. */
  expiresAt: number;
};

const TOKENS_KEY = "vp.auth.tokens";
const PKCE_KEY = "vp.auth.pkce";

export type PkcePending = {
  verifier: string;
  state: string;
};

let memory: AuthTokens | null = null;

function readJson<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function writeJson(key: string, value: unknown): void {
  sessionStorage.setItem(key, JSON.stringify(value));
}

export function getTokens(): AuthTokens | null {
  if (memory) return memory;
  memory = readJson<AuthTokens>(TOKENS_KEY);
  return memory;
}

/** Prefer id_token for API Gateway Cognito JWT authorizer. */
export function getIdToken(): string | null {
  const t = getTokens();
  if (!t?.idToken) return null;
  if (Date.now() >= t.expiresAt - 30_000) return null;
  return t.idToken;
}

/** True when stored tokens exist but id/access are past the soft expiry window. */
export function isAccessExpired(): boolean {
  const t = getTokens();
  if (!t?.idToken) return false;
  return Date.now() >= t.expiresAt - 30_000;
}

export function getRefreshToken(): string | null {
  return getTokens()?.refreshToken ?? null;
}

export function setTokens(tokens: AuthTokens): void {
  memory = tokens;
  writeJson(TOKENS_KEY, tokens);
}

export function clearTokens(): void {
  memory = null;
  sessionStorage.removeItem(TOKENS_KEY);
}

export function savePkcePending(pending: PkcePending): void {
  writeJson(PKCE_KEY, pending);
}

export function takePkcePending(): PkcePending | null {
  const pending = readJson<PkcePending>(PKCE_KEY);
  sessionStorage.removeItem(PKCE_KEY);
  return pending;
}

export function isSignedIn(): boolean {
  if (getIdToken() != null) return true;
  // Soft-expired id/access but refresh_token still present — still a session.
  // Gate/UI should not bounce to landing; ensureIdToken() refreshes before API calls.
  const t = getTokens();
  return Boolean(t?.idToken && t.refreshToken);
}
