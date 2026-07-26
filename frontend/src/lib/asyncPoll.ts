/** Shared backoff for async trip polls (plan-day / crew jobs). */

export type PollSchedule = {
  /** Sleep before the first GET — GenAI jobs almost never finish sooner. */
  quietBeforeFirstMs: number;
  /**
   * Typical earliest completion (rough p50 floor). While elapsed is below this,
   * wait out the remainder instead of polling every few seconds.
   */
  expectedReadyMs: number;
  /** Minimum delay once past expectedReadyMs. */
  minDelayMs: number;
  maxDelayMs: number;
  backoffFactor: number;
};

/** AgentCore day plans are usually tens of seconds; avoid hammering GET. */
export const PLAN_DAY_POLL: PollSchedule = {
  quietBeforeFirstMs: 25_000,
  expectedReadyMs: 50_000,
  minDelayMs: 5_000,
  maxDelayMs: 15_000,
  backoffFactor: 1.4,
};

/** Propose / suggest crews — still LLM-bound, slightly shorter than full days. */
export const CREW_JOB_POLL: PollSchedule = {
  quietBeforeFirstMs: 15_000,
  expectedReadyMs: 30_000,
  minDelayMs: 4_000,
  maxDelayMs: 12_000,
  backoffFactor: 1.4,
};

/**
 * Delay before poll attempt ``attempt`` (0 = before first GET).
 * Prefer waiting until quiet / expected windows using ``startedAtMs`` when known.
 */
export function nextPollDelayMs(
  schedule: PollSchedule,
  args: {
    attempt: number;
    startedAtMs: number | null;
    nowMs?: number;
  },
): number {
  const nowMs = args.nowMs ?? Date.now();
  const attempt = args.attempt;
  const startedAtMs = args.startedAtMs;

  if (attempt <= 0) {
    if (startedAtMs != null) {
      const elapsed = Math.max(0, nowMs - startedAtMs);
      const untilQuiet = schedule.quietBeforeFirstMs - elapsed;
      if (untilQuiet > 0) return untilQuiet;
      // Already past the quiet window (hydrate/resume) — GET immediately.
      return 0;
    }
    return schedule.quietBeforeFirstMs;
  }

  if (startedAtMs != null) {
    const elapsed = Math.max(0, nowMs - startedAtMs);
    const untilExpected = schedule.expectedReadyMs - elapsed;
    if (untilExpected > schedule.minDelayMs) {
      return Math.min(schedule.maxDelayMs, untilExpected);
    }
  }

  const exp =
    schedule.minDelayMs * Math.pow(schedule.backoffFactor, Math.max(0, attempt - 1));
  return Math.min(schedule.maxDelayMs, Math.round(exp));
}

export function parseStartedAtMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

export function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

export function waitUntilVisible(signal?: AbortSignal): Promise<void> {
  if (typeof document === "undefined" || document.visibilityState === "visible") {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const onVis = () => {
      if (document.visibilityState === "visible") {
        cleanup();
        resolve();
      }
    };
    const onAbort = () => {
      cleanup();
      reject(new DOMException("Aborted", "AbortError"));
    };
    const cleanup = () => {
      document.removeEventListener("visibilitychange", onVis);
      signal?.removeEventListener("abort", onAbort);
    };
    document.addEventListener("visibilitychange", onVis);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}
