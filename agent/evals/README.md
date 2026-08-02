# Offline crew evals

Plumbing for golden-set checks against crew JSON outputs. **No AWS required** for harness tests.

Traveler energy: soft overage above comfort; plan-next-day auto-trims at ≥150% when possible; offline `energy_overage_rate` only — see [`docs/PLANNING_QUALITY.md`](../../docs/PLANNING_QUALITY.md).

## Layout

| Path | Purpose |
| --- | --- |
| `case.py` / `harness.py` | Load fixtures + run cases |
| `scorers.py` / `cost.py` | Graded day_plan metrics + token→USD estimate |
| `compare_orchestration.py` | `day_plan` vs `day_plan_single` pairwise decision |
| `fixtures/*.json` | Case inputs + expected hints (`day_plan_*`, `suggest_place_*`, …) |
| `fixtures/*preference*` | Interest / exclusion cases for non-vacuous `preference_relevance_score` |
| `test_harness.py` / `test_compare_orchestration.py` | Smoke tests |
| `runs/` | Live compare raw envelopes (gitignored) |

## Fixture shape

```json
{
  "id": "day_plan_tokyo_day1",
  "crew": "day_plan",
  "inputs": {
    "overnight_city": "Tokyo",
    "day_index": "1",
    "food_crawl_mode": "false",
    "already_visited": ""
  },
  "expected": {
    "min_places": 3,
    "max_places": 6,
    "forbidden_place_keys": [],
    "interests": ["ramen"],
    "excluded_categories": ["nightlife"]
  }
}
```

Crew `inputs` should match BFF string shapes (`food_crawl_mode` `"true"|"false"`, `already_visited` comma-joined). `crew` may also be `day_plan_single` (compare runner overrides crew anyway).

`EvalResult.metrics` holds graded rates (see [`docs/PLANNING_QUALITY.md`](../../docs/PLANNING_QUALITY.md) metric catalog).

**Preference judge backends** (same key `preference_relevance_score`):

| Flag | Backend |
| --- | --- |
| `--preference-judge heuristic` (default) | Deterministic keyword overlap |
| `--preference-judge llm` | Bedrock Converse JSON judge (`EVAL_JUDGE_MODEL_ID`); falls back to heuristic on errors |

**Dashboard:** every CLI run prints an aggregate metrics table. Write a file with `--report reports/metrics.md` or `.json`.

**Persist (durable fair A/B):** write run + case rows to the dedicated metrics DynamoDB table:

```bash
# Local DynamoDB (after ./scripts/dev.sh or create_local_table.py)
export DYNAMODB_ENDPOINT=http://127.0.0.1:8000
export DYNAMODB_METRICS_TABLE_NAME=vacation-planner-local-metrics
export AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local AWS_REGION=us-east-1
uv run python -m evals --persist

# Prod table (real AWS creds; no DYNAMODB_ENDPOINT)
export DYNAMODB_METRICS_TABLE_NAME=vacation-planner-prod-metrics   # terraform output
uv run python -m evals --persist
```

Same `experiment_key` ⇒ comparable runs (fixture suite hash, prompt version/hash, preference judge, judge/model ids, git sha, live flag). Soft-fails by default; use `--persist-required` in CI.

Private SPA: open `/metrics` (Cognito session + `METRICS_ADMIN_SUBS` allowlist). Not linked from the main trip wizard.

Files starting with `_` are ignored.

## Run harness tests

From `agent/` (uses the top-level agent venv):

```bash
cd agent
uv sync
uv run pytest evals/test_harness.py -q
```

## CLI

```bash
cd agent
uv run python -m evals            # score fixtures that have sibling *.output.json
uv run python -m evals --live     # call crew_kickoff (needs credentials)
uv run python -m evals --live --compare-orchestration \
  --report reports/orchestration_compare.md
uv run python -m evals --live --compare-orchestration --orchestration-smoke \
  --report reports/orchestration_compare_smoke.md
uv run python -m evals --preference-judge llm --report reports/metrics.md
uv run python -m evals --persist
```

`--compare-orchestration` runs each `day_plan` fixture under both `day_plan` and `day_plan_single`, saves raw envelopes under `evals/runs/<run_id>/`, and prints a keep/simplify decision against the bar in [`docs/PLANNING_QUALITY.md`](../../docs/PLANNING_QUALITY.md). Live runs set `EVALS_QUIET=1` so CrewAI response panels stay silent; progress is printed to **stderr** (`[n/N] …`) and appended to the report’s **Progress** section (the `.md` is rewritten after each case). The report **Summary** table mirrors the terminal decision table. Use `--sequential-arms` if you need serial execution. Use `--orchestration-smoke` (~8 cases), `--case ID`, or `--max-cases N` for faster live iteration; reserve the full suite for a decision-quality run.

When comparing via **AgentCore** (not in-process kickoff), set `ALLOW_EVAL_CREWS=1` so `day_plan_single` is accepted by `invoke_payload` (production defaults exclude it).

**Learnings** (prompts, Nova ToolUse mitigations, cost/latency/correctness snapshots): see [Orchestration experiment → Learnings](../../docs/PLANNING_QUALITY.md#learnings-2026-07-25--2026-07-26) in `PLANNING_QUALITY.md`.

Offline mode **skips** cases without `fixtures/<id>.output.json` (prints `SKIP`). A golden for `day_plan_example_shape` is included so the default command exits 0.

Optional offline outputs: `fixtures/<id>.output.json` (skipped by the case loader; used only as eval input).

## Extending

Add fixtures with `expected` keys such as `min_places` / `max_places` / `forbidden_place_keys` (day) or `min_cities` / `max_cities` (route). Pair with `*.output.json` for offline CLI runs without `--live`.
