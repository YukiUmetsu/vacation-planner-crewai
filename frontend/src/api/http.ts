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

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers: Record<string, string> = {
    "content-type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (shouldSendDevIdentity() && !headers["x-dev-user-sub"]) {
    headers["x-dev-user-sub"] = DEV_USER;
  }

  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
  });

  const data = (await res.json().catch(() => ({}))) as {
    error?: string;
    code?: string;
  };

  if (!res.ok) {
    throw new ApiError(res.status, data.error ?? res.statusText, data.code);
  }
  return data as T;
}
