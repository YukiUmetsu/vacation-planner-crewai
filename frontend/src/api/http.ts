import { isCognitoConfigured } from "../auth/config";
import { ensureIdToken, logout } from "../auth/oauth";
import { getDevCrewMode, isDevCrewModeUiEnabled } from "../lib/devCrewMode";

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

/** User-facing copy for known API error codes (prefer over raw server text). */
const API_ERROR_MESSAGES: Record<string, string> = {
  free_trip_limit:
    "Free plan includes one trip. Delete it or upgrade to create another.",
  genai_quota_exceeded:
    "You've reached the planning usage limit. Try again later.",
  quality_empty:
    "Not enough open places remained after quality checks. Please try again.",
  dedupe_empty: "All suggested places were already visited. Please try again.",
  missing_meals:
    "That day plan was missing lunch or dinner. Please try planning the day again.",
  food_only_day:
    "That day was all restaurants. Please try again so the plan includes at least one non-food stop.",
  quality_hard_fail:
    "That day plan did not meet quality checks. Please try again.",
  place_weekday_closed:
    "That place is closed on this day of the week. Please try suggesting again.",
  place_closed: "That place is permanently closed. Please try suggesting again.",
  place_duplicate: "That place is already on your trip. Please try suggesting again.",
};

export function messageForApiError(
  status: number,
  code: string | undefined,
  fallback: string,
): string {
  if (code && API_ERROR_MESSAGES[code]) {
    return API_ERROR_MESSAGES[code];
  }
  // Older trips may still store the internal quality_empty detail as planning_error.
  if (/fewer than 3 open places/i.test(fallback)) {
    return API_ERROR_MESSAGES.quality_empty;
  }
  if (status >= 500) {
    return "Something went wrong. Please try again.";
  }
  return fallback;
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
  // Vite DEV only — production builds never send this; API ignores unless AUTH_MODE=dev.
  if (isDevCrewModeUiEnabled() && !headers["x-crew-mode"]) {
    headers["x-crew-mode"] = getDevCrewMode();
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
    const rawDetail = data.error ?? data.message ?? res.statusText;
    const detail = messageForApiError(res.status, code, rawDetail);
    const suffix =
      code && res.status < 500 && !API_ERROR_MESSAGES[code]
        ? ` (${code})`
        : "";
    throw new ApiError(res.status, `${detail}${suffix}`, code);
  }
  return data as T;
}
