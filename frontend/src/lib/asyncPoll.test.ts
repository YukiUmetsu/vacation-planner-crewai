import { describe, expect, it } from "vitest";
import {
  PLAN_DAY_POLL,
  nextPollDelayMs,
  parseStartedAtMs,
} from "./asyncPoll";

describe("nextPollDelayMs", () => {
  const t0 = Date.parse("2026-07-26T12:00:00.000Z");

  it("waits the quiet window before the first poll", () => {
    expect(
      nextPollDelayMs(PLAN_DAY_POLL, {
        attempt: 0,
        startedAtMs: t0,
        nowMs: t0,
      }),
    ).toBe(PLAN_DAY_POLL.quietBeforeFirstMs);
  });

  it("GETs immediately when resuming after quiet already passed", () => {
    expect(
      nextPollDelayMs(PLAN_DAY_POLL, {
        attempt: 0,
        startedAtMs: t0,
        nowMs: t0 + PLAN_DAY_POLL.quietBeforeFirstMs + 5_000,
      }),
    ).toBe(0);
  });

  it("waits out expectedReady before dense polling", () => {
    const afterQuiet = t0 + PLAN_DAY_POLL.quietBeforeFirstMs;
    const delay = nextPollDelayMs(PLAN_DAY_POLL, {
      attempt: 1,
      startedAtMs: t0,
      nowMs: afterQuiet,
    });
    const untilExpected =
      PLAN_DAY_POLL.expectedReadyMs - PLAN_DAY_POLL.quietBeforeFirstMs;
    expect(delay).toBe(Math.min(PLAN_DAY_POLL.maxDelayMs, untilExpected));
  });

  it("backs off after the expected window", () => {
    const afterExpected = t0 + PLAN_DAY_POLL.expectedReadyMs + 1_000;
    expect(
      nextPollDelayMs(PLAN_DAY_POLL, {
        attempt: 1,
        startedAtMs: t0,
        nowMs: afterExpected,
      }),
    ).toBe(PLAN_DAY_POLL.minDelayMs);
    expect(
      nextPollDelayMs(PLAN_DAY_POLL, {
        attempt: 2,
        startedAtMs: t0,
        nowMs: afterExpected,
      }),
    ).toBe(Math.round(PLAN_DAY_POLL.minDelayMs * PLAN_DAY_POLL.backoffFactor));
  });
});

describe("parseStartedAtMs", () => {
  it("parses ISO timestamps", () => {
    expect(parseStartedAtMs("2026-07-26T12:00:00.000Z")).toBe(
      Date.parse("2026-07-26T12:00:00.000Z"),
    );
    expect(parseStartedAtMs(null)).toBeNull();
    expect(parseStartedAtMs("nope")).toBeNull();
  });
});
