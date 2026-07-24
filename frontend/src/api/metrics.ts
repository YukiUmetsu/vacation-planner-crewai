import { apiFetch } from "./http";

export type EvalRunSummary = {
  run_id: string;
  started_at: string;
  experiment_key: string;
  dimensions: Record<string, unknown>;
  aggregates: Record<string, number>;
  case_count: number;
  passed_count: number;
  updated_at?: string;
};

export type EvalCaseDetail = {
  case_id: string;
  passed: boolean;
  failures: string[];
  metrics: Record<string, number | boolean>;
};

export type EvalRunDetail = EvalRunSummary & {
  cases?: EvalCaseDetail[];
};

export type OnlineKind = "quality" | "product";

export type OnlineQualityEvent = {
  event_id: string;
  occurred_at: string;
  experiment_key?: string;
  trip_id?: string;
  day_index?: number;
  passes_relevance?: boolean;
  relevance_score?: number;
  constraint_score?: number;
  failure_tags?: string[];
  crew_name?: string;
  model_id?: string;
  places_count?: number;
};

export type OnlineProductEvent = {
  event_id: string;
  occurred_at: string;
  event_name: string;
  user_sub_hash?: string;
  trip_id?: string;
  day_index?: number;
  payload?: Record<string, unknown>;
};

export function listEvalRuns(opts?: {
  experimentKey?: string;
  limit?: number;
}): Promise<{ runs: EvalRunSummary[] }> {
  const params = new URLSearchParams();
  if (opts?.experimentKey) params.set("experiment_key", opts.experimentKey);
  if (opts?.limit) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return apiFetch(`/admin/metrics/runs${qs ? `?${qs}` : ""}`);
}

export function getEvalRun(
  runId: string,
  startedAt: string,
): Promise<EvalRunDetail> {
  const params = new URLSearchParams();
  // Encode explicitly so ISO offsets never become spaces via "+" semantics.
  params.set("started_at", startedAt);
  return apiFetch(
    `/admin/metrics/runs/${encodeURIComponent(runId)}?${params.toString()}`,
  );
}

export function listOnlineEvents(opts: {
  kind: OnlineKind;
  experimentKey?: string;
  eventName?: string;
  limit?: number;
}): Promise<{ kind: OnlineKind; events: Array<OnlineQualityEvent | OnlineProductEvent> }> {
  const params = new URLSearchParams();
  params.set("kind", opts.kind);
  if (opts.experimentKey) params.set("experiment_key", opts.experimentKey);
  if (opts.eventName) params.set("event_name", opts.eventName);
  if (opts.limit) params.set("limit", String(opts.limit));
  return apiFetch(`/admin/metrics/online?${params.toString()}`);
}
