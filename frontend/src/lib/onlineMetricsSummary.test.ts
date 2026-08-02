import { describe, expect, it } from "vitest";
import {
  formatAcceptSeconds,
  formatRate,
  summarizeProductEvents,
  summarizeQualityEvents,
} from "./onlineMetricsSummary";

describe("summarizeQualityEvents", () => {
  it("separates terminal pass/fail from retries", () => {
    const summary = summarizeQualityEvents([
      {
        event: "plan_day_quality",
        occurred_at: "2026-07-24T10:00:00Z",
        plan_day_attempt: 1,
        failure_tags: ["energy_overload"],
        latency_ms: 2000,
        prompt_tokens: 100,
        completion_tokens: 50,
        total_tokens: 150,
        energy_places_trimmed: 2,
      },
      {
        event: "plan_day_quality",
        occurred_at: "2026-07-24T11:00:00Z",
        guardrail_code: "missing_meals",
        plan_day_attempt: 3,
        latency_ms: 4000,
        prompt_tokens: 200,
        completion_tokens: 100,
        total_tokens: 300,
        energy_places_trimmed: 1,
      },
      {
        event: "plan_day_retry",
        occurred_at: "2026-07-24T10:30:00Z",
        failure_code: "missing_meals",
        latency_ms: 3000,
      },
      {
        event: "plan_day_retry",
        occurred_at: "2026-07-25T09:00:00Z",
        failure_code: "dedupe_empty",
      },
    ]);

    expect(summary.passCount).toBe(1);
    expect(summary.failCount).toBe(1);
    expect(summary.retryCount).toBe(2);
    expect(summary.passRate).toBe(0.5);
    expect(summary.retryShare).toBe(0.5);
    expect(summary.meanTerminalAttempt).toBe(2);
    expect(summary.meanLatencyMs).toBe(3000);
    expect(summary.latencySampleSize).toBe(3);
    expect(summary.meanTotalTokens).toBe(225);
    expect(summary.meanPromptTokens).toBe(150);
    expect(summary.tokenSampleSize).toBe(2);
    expect(summary.energyPlacesTrimmed).toBe(3);
    expect(summary.failByCode).toEqual([
      { label: "missing_meals", count: 1 },
    ]);
    expect(summary.retryByCode.map((r) => r.label).sort()).toEqual([
      "dedupe_empty",
      "missing_meals",
    ]);
    expect(summary.softTags).toEqual([
      { label: "energy_overload", count: 1 },
    ]);
    expect(summary.byDay).toHaveLength(2);
  });

  it("coerces string latency/token fields from API", () => {
    const summary = summarizeQualityEvents([
      {
        event: "plan_day_quality",
        latency_ms: "2500" as unknown as number,
        total_tokens: "400" as unknown as number,
        prompt_tokens: "250" as unknown as number,
        completion_tokens: "150" as unknown as number,
      },
    ]);
    expect(summary.meanLatencyMs).toBe(2500);
    expect(summary.meanTotalTokens).toBe(400);
    expect(summary.latencySampleSize).toBe(1);
  });

  it("treats legacy events without event field as terminal", () => {
    const summary = summarizeQualityEvents([
      { occurred_at: "2026-07-24T10:00:00Z", passes_relevance: true },
      {
        occurred_at: "2026-07-24T11:00:00Z",
        guardrail_code: "quality_empty",
      },
    ]);
    expect(summary.terminalCount).toBe(2);
    expect(summary.retryCount).toBe(0);
    expect(summary.passCount).toBe(1);
  });

  it("does not count passes_relevance false as a pass", () => {
    const summary = summarizeQualityEvents([
      {
        event: "plan_day_quality",
        occurred_at: "2026-07-24T10:00:00Z",
        passes_relevance: false,
      },
      {
        event: "plan_day_quality",
        occurred_at: "2026-07-24T11:00:00Z",
        passes_relevance: true,
      },
    ]);
    expect(summary.passCount).toBe(1);
    expect(summary.failCount).toBe(1);
    expect(summary.passRate).toBe(0.5);
    expect(summary.failByCode).toEqual([
      { label: "passes_relevance_false", count: 1 },
    ]);
  });
});

describe("summarizeProductEvents", () => {
  it("aggregates names and mean accept latency", () => {
    const summary = summarizeProductEvents([
      {
        event_name: "proposal_accepted",
        occurred_at: "2026-07-24T10:00:00Z",
      },
      {
        event_name: "proposal_accepted",
        occurred_at: "2026-07-24T11:00:00Z",
      },
      {
        event_name: "time_to_accept",
        occurred_at: "2026-07-24T11:00:00Z",
        payload: { ms: 1000 },
      },
      {
        event_name: "time_to_accept",
        occurred_at: "2026-07-25T11:00:00Z",
        payload: { ms: 3000 },
      },
    ]);
    expect(summary.sampleSize).toBe(4);
    expect(summary.byEventName[0]).toEqual({
      label: "proposal_accepted",
      count: 2,
    });
    expect(summary.meanAcceptMs).toBe(2000);
    expect(summary.acceptSampleSize).toBe(2);
  });
});

describe("formatRate", () => {
  it("formats null and percents", () => {
    expect(formatRate(null)).toBe("—");
    expect(formatRate(0.5)).toBe("50%");
  });
});

describe("formatAcceptSeconds", () => {
  it("formats ms as seconds", () => {
    expect(formatAcceptSeconds(null)).toBe("—");
    expect(formatAcceptSeconds(2000)).toBe("2.00 s");
    expect(formatAcceptSeconds(12_500)).toBe("12.5 s");
  });

  it("uses 1 decimal when 2-decimal rounding reaches 10s", () => {
    expect(formatAcceptSeconds(9_949)).toBe("9.95 s");
    // 9996–9999 ms are < 10s raw but toFixed(2) rounds to "10.00"
    expect(formatAcceptSeconds(9_996)).toBe("10.0 s");
    expect(formatAcceptSeconds(9_999)).toBe("10.0 s");
    expect(formatAcceptSeconds(10_000)).toBe("10.0 s");
  });
});
