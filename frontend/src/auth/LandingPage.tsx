import { useState } from "react";
import {
  getSocialProviders,
  isEmailAuthEnabled,
  type CognitoIdentityProvider,
} from "./config";
import { beginLogin } from "./oauth";

const SOCIAL_LABELS: Record<string, string> = {
  Google: "Continue with Google",
  Facebook: "Continue with Facebook",
};

/**
 * Full-viewport landing: brand + short line + auth CTAs.
 * Shown when Cognito is configured and the user is not signed in (live mode).
 */
export function LandingPage() {
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const emailEnabled = isEmailAuthEnabled();
  const social = getSocialProviders();

  async function start(
    key: string,
    options: { provider?: CognitoIdentityProvider; mode?: "signin" | "signup" },
  ) {
    setError(null);
    setPending(key);
    try {
      await beginLogin(options);
    } catch (err: unknown) {
      setPending(null);
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="relative flex min-h-dvh flex-col overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 landing-hero-bg"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-sand/80 to-transparent"
      />

      <main className="relative z-10 mx-auto flex w-full max-w-lg flex-1 flex-col justify-center px-6 py-16 sm:px-8">
        <p className="landing-fade-up font-display text-5xl font-semibold tracking-tight text-ink sm:text-6xl">
          Vacation Planner
        </p>
        <p className="landing-fade-up landing-delay-1 mt-4 max-w-md text-lg text-ink-muted">
          Plan calmly — sign in to create your trip.
        </p>

        <div className="landing-fade-up landing-delay-2 mt-10 flex flex-col gap-3">
          {emailEnabled ? (
            <>
              <button
                type="button"
                disabled={pending != null}
                className="rounded-lg bg-teal px-4 py-3 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-60"
                onClick={() =>
                  void start("signin", { provider: "COGNITO", mode: "signin" })
                }
              >
                {pending === "signin" ? "Redirecting…" : "Sign in"}
              </button>
              <button
                type="button"
                disabled={pending != null}
                className="rounded-lg border border-teal bg-surface/80 px-4 py-3 text-sm font-semibold text-teal transition hover:bg-teal-soft disabled:opacity-60"
                onClick={() => void start("signup", { mode: "signup" })}
              >
                {pending === "signup" ? "Redirecting…" : "Sign up"}
              </button>
            </>
          ) : null}

          {social.length > 0 ? (
            <div
              className={
                emailEnabled
                  ? "mt-2 flex flex-col gap-3 border-t border-line/80 pt-5"
                  : "flex flex-col gap-3"
              }
            >
              {social.map((provider) => (
                <button
                  key={provider}
                  type="button"
                  disabled={pending != null}
                  className="rounded-lg border border-line bg-surface px-4 py-3 text-sm font-semibold text-ink transition hover:bg-teal-soft disabled:opacity-60"
                  onClick={() => void start(provider, { provider })}
                >
                  {pending === provider
                    ? "Redirecting…"
                    : (SOCIAL_LABELS[provider] ?? `Continue with ${provider}`)}
                </button>
              ))}
            </div>
          ) : null}
        </div>

        {error ? (
          <p className="mt-4 text-sm text-red-700" role="alert">
            {error}
          </p>
        ) : null}

        <p className="landing-fade-up landing-delay-3 mt-10 text-xs text-ink-muted">
          <a className="underline decoration-line underline-offset-2 hover:text-teal" href="/privacy.html">
            Privacy
          </a>
          {" · "}
          <a
            className="underline decoration-line underline-offset-2 hover:text-teal"
            href="/data-deletion.html"
          >
            Data deletion
          </a>
        </p>
      </main>
    </div>
  );
}
