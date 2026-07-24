import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getEvalRun,
  listEvalRuns,
  listOnlineEvents,
  type EvalRunDetail,
  type EvalRunSummary,
  type OnlineKind,
  type OnlineProductEvent,
  type OnlineQualityEvent,
} from "../api/metrics";
import { ApiError } from "../api/http";
import {
  ensureIdToken,
  isCognitoConfigured,
  isSignedIn,
  LandingPage,
} from "../auth";

function metricKeys(runs: EvalRunSummary[]): string[] {
  const keys = new Set<string>();
  for (const run of runs) {
    for (const key of Object.keys(run.aggregates || {})) {
      keys.add(key);
    }
  }
  return [...keys].sort();
}

function formatMetric(value: number | undefined): string {
  if (value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(3);
}

/**
 * Private metrics dashboard. Not linked from main nav.
 * Requires Cognito session + METRICS_ADMIN_SUBS allowlist on the API.
 */
export function MetricsPage() {
  const cognito = isCognitoConfigured();
  const needsAuth = cognito && !isSignedIn();

  useEffect(() => {
    if (!cognito || !isSignedIn()) return;
    void ensureIdToken();
  }, [cognito]);

  if (needsAuth) {
    return <LandingPage />;
  }

  return <MetricsDashboard />;
}

function MetricsDashboard() {
  const [experimentDraft, setExperimentDraft] = useState("");
  const [experimentFilter, setExperimentFilter] = useState("");
  const [runs, setRuns] = useState<EvalRunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<[string, string][]>([]);
  const [details, setDetails] = useState<EvalRunDetail[]>([]);

  const [onlineKind, setOnlineKind] = useState<OnlineKind>("quality");
  const [onlineEvents, setOnlineEvents] = useState<
    Array<OnlineQualityEvent | OnlineProductEvent>
  >([]);
  const [onlineLoading, setOnlineLoading] = useState(true);
  const [onlineError, setOnlineError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listEvalRuns({
        experimentKey: experimentFilter.trim() || undefined,
        limit: 50,
      });
      setRuns(data.runs);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 403) {
        setError("Forbidden — your Cognito sub is not in METRICS_ADMIN_SUBS.");
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
      setRuns([]);
    } finally {
      setLoading(false);
    }
  }, [experimentFilter]);

  const loadOnline = useCallback(async () => {
    setOnlineLoading(true);
    setOnlineError(null);
    try {
      const data = await listOnlineEvents({ kind: onlineKind, limit: 50 });
      setOnlineEvents(data.events);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 403) {
        setOnlineError(
          "Forbidden — your Cognito sub is not in METRICS_ADMIN_SUBS.",
        );
      } else {
        setOnlineError(err instanceof Error ? err.message : String(err));
      }
      setOnlineEvents([]);
    } finally {
      setOnlineLoading(false);
    }
  }, [onlineKind]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void loadOnline();
  }, [loadOnline]);

  const keys = useMemo(() => metricKeys(runs), [runs]);

  function applyFilter() {
    setSelected([]);
    setDetails([]);
    setExperimentFilter(experimentDraft.trim());
  }

  function toggleSelect(run: EvalRunSummary) {
    setSelected((prev) => {
      const exists = prev.find(
        ([r, s]) => r === run.run_id && s === run.started_at,
      );
      if (exists) {
        return prev.filter(
          ([r, s]) => !(r === run.run_id && s === run.started_at),
        );
      }
      if (prev.length >= 2) {
        return [[run.run_id, run.started_at]];
      }
      return [...prev, [run.run_id, run.started_at]];
    });
  }

  useEffect(() => {
    if (selected.length === 0) {
      setDetails([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const loaded = await Promise.all(
          selected.map(([runId, startedAt]) => getEvalRun(runId, startedAt)),
        );
        if (!cancelled) setDetails(loaded);
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const compareKeys = useMemo(() => {
    const set = new Set<string>();
    for (const d of details) {
      for (const k of Object.keys(d.aggregates || {})) set.add(k);
    }
    return [...set].sort();
  }, [details]);

  return (
    <div className="mx-auto min-h-dvh max-w-5xl px-4 py-10 sm:px-6">
      <header className="mb-8">
        <p className="font-display text-3xl font-semibold tracking-tight text-ink">
          Metrics
        </p>
        <p className="mt-2 max-w-2xl text-sm text-ink-muted">
          Offline eval runs and online quality/product events (also logged to
          CloudWatch). Filter offline runs by{" "}
          <code className="text-teal">experiment_key</code> for fair A/B.
        </p>
      </header>

      <section className="mb-12">
        <h2 className="font-display text-xl font-semibold text-ink">
          Offline eval runs
        </h2>
        <div className="mt-4 mb-6 flex flex-wrap items-end gap-3">
          <label className="flex min-w-[16rem] flex-1 flex-col gap-1 text-sm">
            <span className="text-ink-muted">Experiment key</span>
            <input
              className="rounded border border-line bg-surface px-3 py-2 text-ink outline-none focus:border-teal"
              value={experimentDraft}
              onChange={(e) => setExperimentDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") applyFilter();
              }}
              placeholder="optional filter"
              spellCheck={false}
            />
          </label>
          <button
            type="button"
            className="rounded bg-teal px-4 py-2 text-sm font-medium text-white hover:bg-teal-deep"
            onClick={() => {
              if (experimentDraft.trim() !== experimentFilter) {
                applyFilter();
              } else {
                void load();
              }
            }}
          >
            Refresh
          </button>
        </div>

        {error ? (
          <p className="mb-4 rounded border border-warn/40 bg-warn-soft px-3 py-2 text-sm text-warn">
            {error}
          </p>
        ) : null}

        {loading ? (
          <p className="text-sm text-ink-muted">Loading runs…</p>
        ) : runs.length === 0 ? (
          <p className="text-sm text-ink-muted">
            No runs yet. Persist with{" "}
            <code className="text-teal">uv run python -m evals --persist</code>.
          </p>
        ) : (
          <div className="overflow-x-auto rounded border border-line bg-surface/80">
            <table className="metrics-table w-full min-w-[40rem] text-left text-sm">
              <thead>
                <tr className="border-b border-line text-ink-muted">
                  <th className="px-3 py-2 font-medium">Compare</th>
                  <th className="px-3 py-2 font-medium">Started</th>
                  <th className="px-3 py-2 font-medium">Experiment</th>
                  <th className="px-3 py-2 font-medium">Pass</th>
                  {keys.slice(0, 4).map((k) => (
                    <th key={k} className="px-3 py-2 font-medium">
                      {k}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const checked = selected.some(
                    ([r, s]) => r === run.run_id && s === run.started_at,
                  );
                  return (
                    <tr
                      key={`${run.run_id}-${run.started_at}`}
                      className="border-b border-line/70 last:border-0"
                    >
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleSelect(run)}
                          aria-label={`Select run ${run.run_id}`}
                        />
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap text-ink-muted">
                        {run.started_at.slice(0, 19)}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">
                        {run.experiment_key}
                      </td>
                      <td className="px-3 py-2">
                        {run.passed_count}/{run.case_count}
                      </td>
                      {keys.slice(0, 4).map((k) => (
                        <td key={k} className="px-3 py-2 tabular-nums">
                          {formatMetric(run.aggregates?.[k])}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {details.length > 0 ? (
          <div className="mt-10">
            <h3 className="font-display text-lg font-semibold text-ink">
              Compare ({details.length})
            </h3>
            <div className="mt-4 overflow-x-auto rounded border border-line bg-surface/80">
              <table className="metrics-table w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-ink-muted">
                    <th className="px-3 py-2 font-medium">Metric</th>
                    {details.map((d) => (
                      <th
                        key={d.run_id}
                        className="px-3 py-2 font-mono text-xs font-medium"
                      >
                        {d.run_id}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {compareKeys.map((k) => (
                    <tr
                      key={k}
                      className="border-b border-line/70 last:border-0"
                    >
                      <td className="px-3 py-2 text-ink-muted">{k}</td>
                      {details.map((d) => (
                        <td
                          key={d.run_id}
                          className="px-3 py-2 tabular-nums"
                        >
                          {formatMetric(d.aggregates?.[k])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {details.map((d) => (
              <details key={d.run_id} className="mt-4 text-sm">
                <summary className="cursor-pointer text-teal">
                  Cases for {d.run_id} ({d.cases?.length ?? 0})
                </summary>
                <ul className="mt-2 space-y-1 text-ink-muted">
                  {(d.cases || []).map((c) => (
                    <li key={c.case_id}>
                      {c.passed ? "PASS" : "FAIL"} {c.case_id}
                    </li>
                  ))}
                </ul>
              </details>
            ))}
          </div>
        ) : null}
      </section>

      <section>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-xl font-semibold text-ink">
            Online events
          </h2>
          <div className="flex items-center gap-2 text-sm">
            <label className="flex items-center gap-2 text-ink-muted">
              Kind
              <select
                className="rounded border border-line bg-surface px-2 py-1 text-ink"
                value={onlineKind}
                onChange={(e) =>
                  setOnlineKind(e.target.value as OnlineKind)
                }
              >
                <option value="quality">quality</option>
                <option value="product">product</option>
              </select>
            </label>
            <button
              type="button"
              className="rounded bg-teal px-3 py-1.5 text-sm font-medium text-white hover:bg-teal-deep"
              onClick={() => void loadOnline()}
            >
              Refresh
            </button>
          </div>
        </div>

        {onlineError ? (
          <p className="mt-4 rounded border border-warn/40 bg-warn-soft px-3 py-2 text-sm text-warn">
            {onlineError}
          </p>
        ) : null}

        {onlineLoading ? (
          <p className="mt-4 text-sm text-ink-muted">Loading online events…</p>
        ) : onlineEvents.length === 0 ? (
          <p className="mt-4 text-sm text-ink-muted">
            No online {onlineKind} events yet.
          </p>
        ) : onlineKind === "quality" ? (
          <div className="mt-4 overflow-x-auto rounded border border-line bg-surface/80">
            <table className="metrics-table w-full text-left text-sm">
              <thead>
                <tr className="border-b border-line text-ink-muted">
                  <th className="px-3 py-2 font-medium">When</th>
                  <th className="px-3 py-2 font-medium">Trip</th>
                  <th className="px-3 py-2 font-medium">Day</th>
                  <th className="px-3 py-2 font-medium">Pass</th>
                  <th className="px-3 py-2 font-medium">Crew</th>
                  <th className="px-3 py-2 font-medium">Experiment</th>
                </tr>
              </thead>
              <tbody>
                {(onlineEvents as OnlineQualityEvent[]).map((ev) => (
                  <tr
                    key={ev.event_id}
                    className="border-b border-line/70 last:border-0"
                  >
                    <td className="px-3 py-2 whitespace-nowrap text-ink-muted">
                      {(ev.occurred_at || "").slice(0, 19)}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {ev.trip_id || "—"}
                    </td>
                    <td className="px-3 py-2">{ev.day_index ?? "—"}</td>
                    <td className="px-3 py-2">
                      {ev.passes_relevance === true
                        ? "yes"
                        : ev.passes_relevance === false
                          ? "no"
                          : "—"}
                    </td>
                    <td className="px-3 py-2">{ev.crew_name || "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {ev.experiment_key || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="mt-4 overflow-x-auto rounded border border-line bg-surface/80">
            <table className="metrics-table w-full text-left text-sm">
              <thead>
                <tr className="border-b border-line text-ink-muted">
                  <th className="px-3 py-2 font-medium">When</th>
                  <th className="px-3 py-2 font-medium">Event</th>
                  <th className="px-3 py-2 font-medium">Trip</th>
                  <th className="px-3 py-2 font-medium">Day</th>
                  <th className="px-3 py-2 font-medium">Payload</th>
                </tr>
              </thead>
              <tbody>
                {(onlineEvents as OnlineProductEvent[]).map((ev) => (
                  <tr
                    key={ev.event_id}
                    className="border-b border-line/70 last:border-0"
                  >
                    <td className="px-3 py-2 whitespace-nowrap text-ink-muted">
                      {(ev.occurred_at || "").slice(0, 19)}
                    </td>
                    <td className="px-3 py-2">{ev.event_name}</td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {ev.trip_id || "—"}
                    </td>
                    <td className="px-3 py-2">{ev.day_index ?? "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs text-ink-muted">
                      {JSON.stringify(ev.payload || {})}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
