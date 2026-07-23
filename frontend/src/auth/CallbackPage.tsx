import { useEffect, useState } from "react";
import { completeLoginFromRedirect } from "./oauth";

/**
 * Route target for Cognito callback_urls (default: http://localhost:5173/callback).
 * Orchestration only — token exchange lives in your oauth.ts stub.
 */
export function CallbackPage() {
  const [message, setMessage] = useState("Signing you in…");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const ok = await completeLoginFromRedirect();
        if (cancelled) return;
        if (!ok) {
          setMessage("Missing authorization code. Return home and try again.");
          return;
        }
        window.history.replaceState({}, "", "/");
        window.location.assign("/");
      } catch (err) {
        if (cancelled) return;
        setMessage(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto flex min-h-dvh max-w-lg flex-col justify-center px-4">
      <p className="font-display text-2xl font-semibold text-ink">Vacation Planner</p>
      <p className="mt-3 text-sm text-ink-muted" role="status">
        {message}
      </p>
      <a href="/" className="mt-6 text-sm font-semibold text-teal underline">
        Back home
      </a>
    </div>
  );
}
