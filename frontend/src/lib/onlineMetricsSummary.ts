/**
 * Client-side aggregates for the private /metrics online dashboard.
 * Derived from recent ONLINE#QUALITY / ONLINE#PRODUCT events (not CloudWatch).
 */

export type QualityEventLike = {
  event?: string;
  occurred_at?: string;
  guardrail_code?: string;
  failure_code?: string;
  failure_tags?: string[];
  plan_day_attempt?: number;
  passes_relevance?: boolean;
  latency_ms?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
};

export type ProductEventLike = {
  event_name: string;
  occurred_at?: string;
  payload?: Record<string, unknown>;
};

export type CountRow = { label: string; count: number };

export type DayBucket = {
  day: string;
  pass: number;
  fail: number;
  retry: number;
};

export type QualitySummary = {
  sampleSize: number;
  terminalCount: number;
  passCount: number;
  failCount: number;
  retryCount: number;
  /** pass / (pass + fail); null when no terminal outcomes. */
  passRate: number | null;
  /** Retries as a share of all sampled quality events. */
  retryShare: number | null;
  /** Mean plan_day_attempt among terminal events that set it. */
  meanTerminalAttempt: number | null;
  /** Mean BFF crew latency_ms across events that set it. */
  meanLatencyMs: number | null;
  latencySampleSize: number;
  /** Mean total_tokens (falls back to prompt+completion when needed). */
  meanTotalTokens: number | null;
  meanPromptTokens: number | null;
  meanCompletionTokens: number | null;
  tokenSampleSize: number;
  failByCode: CountRow[];
  retryByCode: CountRow[];
  softTags: CountRow[];
  byDay: DayBucket[];
};

export type ProductSummary = {
  sampleSize: number;
  byEventName: CountRow[];
  /** Mean payload.ms for time_to_accept events only. */
  meanAcceptMs: number | null;
  acceptSampleSize: number;
  byDay: CountRow[];
};

function isRetry(ev: QualityEventLike): boolean {
  return ev.event === "plan_day_retry";
}

function isTerminalFail(ev: QualityEventLike): boolean {
  if (isRetry(ev)) return false;
  return Boolean(ev.guardrail_code) || ev.passes_relevance === false;
}

function isTerminalPass(ev: QualityEventLike): boolean {
  // Align with MetricsPage outcome labels: only count as pass when relevance
  // is not explicitly false (missing/true both count as pass for KPI).
  return !isRetry(ev) && !ev.guardrail_code && ev.passes_relevance !== false;
}

function dayKey(occurredAt: string | undefined): string {
  if (!occurredAt) return "unknown";
  return occurredAt.slice(0, 10) || "unknown";
}

function countMapToRows(
  counts: Map<string, number>,
  limit = 8,
): CountRow[] {
  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
    .slice(0, limit);
}

function bump(map: Map<string, number>, key: string, by = 1): void {
  map.set(key, (map.get(key) || 0) + by);
}

function asNonNegNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const n = Number(value);
    if (Number.isFinite(n) && n >= 0) return n;
  }
  return null;
}

export function summarizeQualityEvents(
  events: QualityEventLike[],
): QualitySummary {
  const failByCode = new Map<string, number>();
  const retryByCode = new Map<string, number>();
  const softTags = new Map<string, number>();
  const dayMap = new Map<string, DayBucket>();

  let passCount = 0;
  let failCount = 0;
  let retryCount = 0;
  let attemptSum = 0;
  let attemptN = 0;
  let latencySum = 0;
  let latencyN = 0;
  let totalTokSum = 0;
  let promptTokSum = 0;
  let completionTokSum = 0;
  let promptTokN = 0;
  let completionTokN = 0;
  let totalTokN = 0;

  for (const ev of events) {
    const day = dayKey(ev.occurred_at);
    let bucket = dayMap.get(day);
    if (!bucket) {
      bucket = { day, pass: 0, fail: 0, retry: 0 };
      dayMap.set(day, bucket);
    }

    const latency = asNonNegNumber(ev.latency_ms);
    if (latency !== null) {
      latencySum += latency;
      latencyN += 1;
    }

    const prompt = asNonNegNumber(ev.prompt_tokens);
    const completion = asNonNegNumber(ev.completion_tokens);
    let total = asNonNegNumber(ev.total_tokens);
    if (total === null && prompt !== null && completion !== null) {
      total = prompt + completion;
    }
    if (prompt !== null) {
      promptTokSum += prompt;
      promptTokN += 1;
    }
    if (completion !== null) {
      completionTokSum += completion;
      completionTokN += 1;
    }
    if (total !== null) {
      totalTokSum += total;
      totalTokN += 1;
    }

    if (isRetry(ev)) {
      retryCount += 1;
      bucket.retry += 1;
      bump(retryByCode, ev.failure_code || "unknown");
      continue;
    }

    if (isTerminalFail(ev)) {
      failCount += 1;
      bucket.fail += 1;
      bump(
        failByCode,
        String(ev.guardrail_code || "passes_relevance_false"),
      );
    } else if (isTerminalPass(ev)) {
      passCount += 1;
      bucket.pass += 1;
    }

    const attempt = ev.plan_day_attempt;
    if (typeof attempt === "number" && Number.isFinite(attempt) && attempt > 0) {
      attemptSum += attempt;
      attemptN += 1;
    }

    for (const tag of ev.failure_tags || []) {
      const t = String(tag || "").trim();
      if (t) bump(softTags, t);
    }
  }

  const terminalCount = passCount + failCount;
  const sampleSize = events.length;

  const byDay = [...dayMap.values()].sort((a, b) =>
    a.day.localeCompare(b.day),
  );

  return {
    sampleSize,
    terminalCount,
    passCount,
    failCount,
    retryCount,
    passRate: terminalCount > 0 ? passCount / terminalCount : null,
    retryShare: sampleSize > 0 ? retryCount / sampleSize : null,
    meanTerminalAttempt: attemptN > 0 ? attemptSum / attemptN : null,
    meanLatencyMs: latencyN > 0 ? latencySum / latencyN : null,
    latencySampleSize: latencyN,
    meanTotalTokens: totalTokN > 0 ? totalTokSum / totalTokN : null,
    meanPromptTokens: promptTokN > 0 ? promptTokSum / promptTokN : null,
    meanCompletionTokens:
      completionTokN > 0 ? completionTokSum / completionTokN : null,
    tokenSampleSize: totalTokN,
    failByCode: countMapToRows(failByCode),
    retryByCode: countMapToRows(retryByCode),
    softTags: countMapToRows(softTags),
    byDay,
  };
}

export function summarizeProductEvents(
  events: ProductEventLike[],
): ProductSummary {
  const byName = new Map<string, number>();
  const byDay = new Map<string, number>();
  let acceptSum = 0;
  let acceptN = 0;

  for (const ev of events) {
    bump(byName, ev.event_name || "unknown");
    bump(byDay, dayKey(ev.occurred_at));
    if (ev.event_name === "time_to_accept") {
      const ms = ev.payload?.ms;
      if (typeof ms === "number" && Number.isFinite(ms) && ms >= 0) {
        acceptSum += ms;
        acceptN += 1;
      }
    }
  }

  return {
    sampleSize: events.length,
    byEventName: countMapToRows(byName, 12),
    meanAcceptMs: acceptN > 0 ? acceptSum / acceptN : null,
    acceptSampleSize: acceptN,
    byDay: countMapToRows(byDay, 14).sort((a, b) =>
      a.label.localeCompare(b.label),
    ),
  };
}

export function formatRate(rate: number | null): string {
  if (rate === null || Number.isNaN(rate)) return "—";
  return `${(rate * 100).toFixed(0)}%`;
}

export function formatNumber(value: number | null, digits = 1): string {
  if (value === null || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export function formatLatencyMs(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  if (value >= 10_000) return `${(value / 1000).toFixed(1)}s`;
  if (value >= 1000) return `${(value / 1000).toFixed(2)}s`;
  return `${Math.round(value)} ms`;
}

/** Wall-clock accept latency for product metrics — always seconds. */
export function formatAcceptSeconds(ms: number | null): string {
  if (ms === null || Number.isNaN(ms)) return "—";
  const seconds = ms / 1000;
  // Threshold on rounded hundredths so 9996–9999ms → "10.0 s", not "10.00 s".
  const roundedHundredths = Math.round(seconds * 100) / 100;
  if (roundedHundredths >= 10) return `${seconds.toFixed(1)} s`;
  return `${seconds.toFixed(2)} s`;
}

export function formatTokenCount(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  if (value >= 10_000) return `${(value / 1000).toFixed(1)}k`;
  return String(Math.round(value));
}
