import { isCognitoConfigured } from "../auth/config";
import { ensureIdToken, logout } from "../auth/oauth";

const DEV_USER = "local-dev-user";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Base URL for API calls. Prefer VITE_API_URL in prod; default `/api` for Vite proxy. */
export function getApiBaseUrl(): string {
  const fromEnv = import.meta.env.VITE_API_URL;
  if (typeof fromEnv === "string" && fromEnv.trim().length > 0) {
    return fromEnv.replace(/\/$/, "");
  }
  return "/api";
}

/** Dev-only identity header for local AUTH_MODE=dev. Never send in production builds. */
export function shouldSendDevIdentity(): boolean {
  return import.meta.env.DEV === true;
}

/** Shared auth headers for apiFetch and raw fetch (plan-next-day). */
export async function buildAuthHeaders(
  extra?: Record<string, string>,
): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    "content-type": "application/json",
    ...extra,
  };
  const idToken = await ensureIdToken();
  if (idToken) {
    headers.Authorization = `Bearer ${idToken}`;
  } else if (shouldSendDevIdentity() && !headers["x-dev-user-sub"]) {
    headers["x-dev-user-sub"] = DEV_USER;
  }
  return headers;
}

function rejectUnauthorized(): never {
  if (isCognitoConfigured()) {
    logout();
  }
  throw new ApiError(
    401,
    "Session expired or missing — sign in again.",
    "unauthorized",
  );
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = await buildAuthHeaders(
    init?.headers as Record<string, string> | undefined,
  );

  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
  });

  const data = (await res.json().catch(() => ({}))) as {
    error?: string;
    message?: string;
    code?: string;
  };

  if (!res.ok) {
    if (res.status === 401) {
      rejectUnauthorized();
    }
    const code = data.code;
    // Never surface 5xx / agent internals (paths, SDK text) in the UI.
    const detail =
      res.status >= 500
        ? "Something went wrong. Please try again."
        : (data.error ?? data.message ?? res.statusText);
    const suffix = code && res.status < 500 ? ` (${code})` : "";
    throw new ApiError(res.status, `${detail}${suffix}`, code);
  }
  return data as T;
}
