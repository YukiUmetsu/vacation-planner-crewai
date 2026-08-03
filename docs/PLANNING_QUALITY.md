# Planning quality, safety, and evals

Canonical product rules for how we judge a day’s plan. Package READMEs hold implementation detail; this doc is the shared contract.

## Doc map (safety / guardrails / evals)

| Topic | Where |
| --- | --- |
| **Traveler energy ↔ day load** | This file (canonical thresholds) |
| **Input safety (prompt injection / harmful prefs)** | [`backend/src/safety/`](../backend/src/safety/), [ADR 007](./architecture-decisions/007-ai-input-output-safety.md), [`backend/README.md`](../backend/README.md) (`SAFETY_MODE`, `SAFETY_OUTPUT_MODE`) |
| **Bedrock Guardrail policies + IAM** | [`infra/README.md`](../infra/README.md) (Guardrails section), [`infra/guardrails/`](../infra/guardrails/) |
| **Offline crew evals** | [`agent/evals/README.md`](../agent/evals/README.md) |
| **AgentCore trust boundary** | [ADR 003](./architecture-decisions/003-bff-agentcore-runtime-only.md) |

### Safety metrics (CloudWatch)

`SAFETY_METRIC` JSON lines (never include full traveler/AI text):

```
fields @timestamp, direction, source, mode, intervened, output_mode, unavailable, safety_latency_ms, trip_id
| filter @message like /SAFETY_METRIC/
| sort @timestamp desc
| limit 50
```

Ship with `SAFETY_OUTPUT_MODE=observe` (would-block logged, plans still persist); flip to `enforce` after soak.

---

## Energy level → warning thresholds

Traveler **energy level** is an integer **1–5** (signal bars in the profile UI).

**What we measure:** total planned minutes for one day =

- sum of place `estimated_minutes` (activity), plus  
- sum of `travel_minutes_from_previous` between stops (travel).

Canonical minute table (keep in sync):

- Frontend: `frontend/src/lib/energyLevel.ts` (`MAX_COMFORTABLE_TOTAL_MINUTES`)
- Backend: `backend/src/shared/energy.py`
- Offline scorers: `agent/evals/scorers.py`

### Warning thresholds (canonical)

| Energy | Meaning (short) | Warn after (activity + travel) | Minutes | Soft target places |
| --- | --- | --- | ---: | ---: |
| **1** | Very low — limited mobility / long rests | **4.5 hours** | 270 | 3 |
| **2** | Low — short days, frequent breaks | **6.5 hours** | 390 | 4 |
| **3** | Moderate — average adult day (default) | **8.5 hours** | 510 | **5** |
| **4** | High — long active days | **12 hours** | 720 | **6** |
| **5** | Very high — packed itineraries OK | **14 hours** | 840 | **7** |

Soft target (`target_place_count`) is passed to the day_plan crew. Lunch and dinner count toward the total, so energy **3** aims for ~5 stops (e.g. lunch + ~3 activities + dinner), not a thin 3-stop day. Hard schema remains **3–7**; BFF does not reject under-target counts.

### Energy Enforcement

| Layer | Behavior |
| --- | --- |
| **Frontend** | Soft banner via `assessDayEnergyLoad` (`ok` / `caution` / `overloaded`) |
| **Crew prompts** | `energy_level` + `max_comfortable_minutes` + `target_place_count` / `remaining_minutes` in day_plan + suggest_place |
| **API** | Soft `energy_overload` tag above comfort; **plan-next-day** at ≥ **150%** trims optional tail stops when possible (`energy_places_trimmed` on `QUALITY_METRIC`). **Suggest-place** never removes existing stops; `remaining_minutes` is clamped to ≥0 |
| **Offline evals** | Overage tracked as `energy_overage_rate` (&gt; comfort); energy does **not** fail `hard_constraint_pass`. Scorers score raw crew JSON (no BFF trim simulation) |

### Severity bands (product)

Let `ratio = totalMinutes / comfortMaxMinutes`.

| Band | Condition | Persist? | UI / tags |
| --- | --- | --- | --- |
| `ok` | `ratio ≤ 1` | Yes | No warning |
| `caution` (soft) | `1 < ratio ≤ 1.2` | Yes | Soft “a bit packed”; BFF soft tag `energy_overload` |
| `overloaded` (soft UI) | `1.2 < ratio < 1.5` | Yes | Stronger “too full” banner; still soft-tagged, still persists |
| `auto-trim target` | `ratio ≥ 1.5` | Yes when still valid | BFF trims optional generated day stops when possible; otherwise persists with soft `energy_overload` (3-stop / all-protected edge may remain at exactly 150%) |

Example: energy **3** → comfort **510** min. **540** → soft caution. **620** → soft overloaded UI (persist). **770** (≥765) → generated day plans are trimmed when optional stops can be removed.

---

## Related hard checks (today)

| Check | Layer |
| --- | --- |
| Dedupe places across days (`place_key`) | Backend `dedupe_places` + crew `already_visited` prompt |
| Crew input size (token proxy) | BFF `crew_io.context_budget.slim_crew_inputs` — only when over `CREW_INPUT_MAX_CHARS`; cut order: `already_visited` → `prior_days_summary` → `city_route_json` → `preferences`. Full visited list still used for dedupe / quality. Large context fields (`already_visited`, `preferences`, `interests`) are interpolated once in the research task; later tasks remind without re-listing. |
| Place count 3–7 / schema | Agent `DayPlan` Pydantic + eval scorers |
| Permanently closed / weekday-closed | Crew reviewer + **Places BFF enrich** (Google outside mainland China; Amap for mainland) + `place_quality` + scorers |
| Energy budget | Crew prompts + BFF soft tag above comfort; generated day auto-trim at ≥150% where possible + scorer metrics |
| Lunch + dinner food stops | Crew prompts + `DayPlan` Pydantic (≥2 `category=food`) + BFF `require_meal_stops` + scorers |
| Day balance (≥1 non-food unless food crawl) | Crew prompts (`food_crawl_mode` / `min_non_food_places`) + BFF `require_day_balance` / `require_suggested_place_balance` + scorers |
| Structured relevance (MVP) | Reviewer `QualityReport` in CrewEnvelope; BFF blocks **hard** tags only; soft tags logged (`QUALITY_METRIC`) |
| Invocation version metadata | `invocation` on CrewEnvelope (`prompt_version`, `prompt_hash`, `model_id`, `git_sha`, …) |
| Online product events | `POST /events` → `PRODUCT_METRIC` logs (accept / delete / regenerate / …) |
| Suggest one more place | `suggest_place` crew + `validate_suggested_place` + `score_suggest_place` |
| Profile prefs / energy / interests | DynamoDB `PROFILE` injected into plan-next-day + suggest-place |
| User preference / destination text safety | Backend safety gate (keyword or ApplyGuardrail) |

---

## Quality layers (MVP)

| Layer | What it does | Blocks persist? |
| --- | --- | --- |
| **1. Deterministic BFF** | Dedupe, Places enrich, closed/weekday, energy soft-tag + generated-day trimming at ≥150%, meal stops, day balance (`place_quality` / `require_meal_stops` / `require_day_balance`) | Yes for existing hard `ApiError` codes; energy overage does **not** block |
| **2. Reviewer `QualityReport`** | Scores + `failure_tags` on CrewEnvelope; soft preference fit | Hard tags only (see table below) |
| **3. Offline / online metrics** | Eval `metrics` aggregates; `QUALITY_METRIC` / `PRODUCT_METRIC` logs | No (observe only) |

Persisted Dynamo DAY items stay **domain-only** — quality/invocation are never written. See [ADR 004](./architecture-decisions/004-crew-quality-envelope.md).

### Day balance (category mix)

Unless the traveler explicitly asked for a **food crawl / restaurant tour / tasting day** (`food_crawl_mode`), a full day (3+ places) must include **at least one non-food** stop (`category != food`). Bare interest in “food” or “ramen” does **not** enable crawl mode.

| Layer | Behavior |
| --- | --- |
| **Crew inputs** | BFF sets `food_crawl_mode`, `min_non_food_places`, `day_shape_hint`; guidance prepended into `preferences` |
| **Energy budget** | Soft `energy_overload` above comfort; plan-next-day trims optional tail stops at ≥150% when possible; suggest-place soft-tags only |
| **BFF tripwire** | `require_day_balance` → `food_only_day`; suggest-place rejects another food when the day still has zero non-food |
| **Offline evals** | Scorers fail food-only days; metrics `non_food_place_count`, `food_only_day_rate` |

### Suggest-place one-off hint vs trip preferences

When the user sends a one-off `hint` on suggest-place, that hint is the **primary** request for that stop:

| Rule | Behavior |
| --- | --- |
| **Crew inputs** | `hint` stays its own field; trip/profile `preferences` / `interests` are labeled secondary (only if compatible with the hint) |
| **Day-balance waive** | Only **food-like** hints (`lunch`, `ramen`, …) waive `prefer_non_food`; kids/activity hints do not |
| **Hard match check** | Food-like hints require food; clear non-food categories must match; substantive free-text without a food phrase rejects food (`hint_mismatch`, retried). Proximity/vibe-only hints (“near Shinjuku station”, “somewhere in Ueno”) stay ambiguous even with named places. |

### Hard vs soft failure tags

| Tag | Class | MVP behavior |
| --- | --- | --- |
| `duplicate_place`, `wrong_city`, `closed_place`, `excluded_category`, `food_only_day` | **Hard** | Fail / regenerate; log `QUALITY_METRIC` |
| `missing_meals` | **Soft** | Retry for better meals; if still incomplete, **persist the day** and log `missing_meals` |
| `too_packed`, `energy_overload` | **Soft** | Log / UI caution; **persist**. Plan-next-day may trim optional stops first at ≥150%; suggest-place never auto-removes existing stops |
| `preference_mismatch`, `too_far`, `weak_reason`, `ungrounded_place`, `weak_day_balance` | **Soft** | Log only; still persist if hard gates pass |

### Metric catalog

**Runtime (`QUALITY_METRIC` JSON line)** — terminal day outcome only (`event=plan_day_quality`): `trip_id`, `day_index`, `passes_relevance`, `relevance_score`, `constraint_score`, `failure_tags`, `guardrail_code` (set only on hard fail), `places_count`, optional `energy_places_trimmed` (optional stops dropped by BFF auto-trim at ≥150%), `plan_day_attempt` (1-based attempt that produced this outcome), `latency_ms` (BFF wall clock for that crew call), `prompt_tokens` / `completion_tokens` / `total_tokens` (from CrewAI when AgentCore/local; absent in fake mode), plus invocation `crew_name`, `prompt_version`, `prompt_hash`, `model_id`, `git_sha`, `input_context_chars`, `context_was_slimmed`, `output_schema_version`.

**Runtime (`RETRY_METRIC` JSON line)** — intermediate recovery (`event=plan_day_retry`): emitted when a hard gate fails **and** another crew attempt will run. Fields: `attempt`, `next_attempt`, `failure_code` (`quality_empty` / `dedupe_empty` / `missing_meals` / `food_only_day`), `places_count`, same latency/token dims when present, plus the same invocation dims. **Do not** count these as terminal failures; pair with a later `QUALITY_METRIC` for the final outcome.

Useful rates (derive in Logs Insights): empty/dedupe/closed/energy/meals/safety/context-truncation from `guardrail_code` + tag counts; silent recovery rate from `RETRY_METRIC` counts vs days that later succeed; `stats avg(latency_ms), avg(total_tokens)`.

**Offline evals (`EvalResult.metrics`)** — per case then mean via `aggregate_metrics`:

| Key | Meaning |
| --- | --- |
| `schema_valid` / `schema_valid_rate` | Shape checks only (place count bounds, keys, overnight city) |
| `hard_constraint_pass` / `_rate` | No hard scorer failures: schema **plus** closed/weekday, meals, day balance, visited/forbidden (energy is **not** a hard scorer failure) |
| `preference_relevance_score` | Interest/keyword overlap (0–1) |
| `explicit_exclusion_violation_rate` | `already_visited` or `excluded_categories` hit |
| `duplicate_rate`, `closed_place_rate`, `closed_place_case_rate`, `energy_overage_rate`, `grounding_rate` | Structural rates (`energy_overage_rate` = any minutes above comfort on raw crew output; production may later trim ≥150% days) |
| `missing_meals_rate`, `wrong_city_rate` | Meal / overnight mismatches |
| `non_food_place_count`, `food_only_day_rate` | Day-balance rates (food-only days should be 0 unless crawl) |
| `latency_ms` | Wall-clock per case (offline harness); online uses BFF `latency_ms` on quality events |
| `cost` / `cost_usd` | Estimated USD from invocation tokens (Nova Pro rate table); omitted when tokens missing |

Preference fixtures: `day_plan_preference_food`, `day_plan_preference_exclusion`, `day_plan_preference_mismatch`. Balance fixtures: `day_plan_balance_food_forward` (pass), `day_plan_balance_food_only` (scorer negative case; no offline golden).

**Phase 2.1 — LLM-as-judge:** same metric keys; swap the scorer backend for `preference_relevance_score` only via `uv run python -m evals --preference-judge llm` (`EVAL_JUDGE_MODEL_ID` / Bedrock Converse). Default remains heuristic. Offline dashboard: CLI prints aggregate rates and optional `--report path.md|.json`.

**Durable store + private UI:** `uv run python -m evals --persist` writes run/case rows to the dedicated metrics DynamoDB table (`DYNAMODB_METRICS_TABLE_NAME`). Fair A/B uses deterministic `experiment_key` (fixture suite + prompt + judge + model + git + live). Private SPA at `/metrics` (no main-nav link); API `GET /admin/metrics/runs` gated by `METRICS_ADMIN_SUBS`.

**Online dual-write:** `QUALITY_METRIC` / `RETRY_METRIC` / `PRODUCT_METRIC` still emit CloudWatch log lines **and** append to the same metrics table (`ONLINE#QUALITY` / `ONLINE#PRODUCT`). Distinguish quality vs retry via payload `event` (`plan_day_quality` vs `plan_day_retry`). Dynamo failures soft-fail so planning/`POST /events` never break. List via `GET /admin/metrics/online?kind=quality|product`. The private `/metrics` SPA shows **aggregates** (pass rate, retry counts, stacked day bars, fail/retry code charts) over the latest 200 events per kind; raw rows stay under collapsible “Recent …” sections.

**Online product (`PRODUCT_METRIC` via `POST /events`)** — allowlisted names: `proposal_accepted`, `proposal_accepted_without_edit`, `manual_edit`, `time_to_accept` (payload `ms`), `plan_regenerated`, `place_deleted`, `suggestion_accepted`, `place_reordered` (payload `from_index`/`to_index`). No PII; `user_sub_hash` is peppered SHA-256.

### CloudWatch Logs Insights (examples)

```
fields @timestamp, trip_id, day_index, failure_tags, guardrail_code, plan_day_attempt, latency_ms, total_tokens, prompt_version
| filter @message like /QUALITY_METRIC/
| sort @timestamp desc
| limit 50
```

```
fields @timestamp, trip_id, day_index, attempt, next_attempt, failure_code, latency_ms, total_tokens, prompt_version
| filter @message like /RETRY_METRIC/
| stats count() by failure_code
```

```
fields latency_ms, total_tokens
| filter @message like /QUALITY_METRIC/ or @message like /RETRY_METRIC/
| stats avg(latency_ms), pct(latency_ms, 90), avg(total_tokens) by bin(1d)
```

```
fields @timestamp, event_name, trip_id, payload.ms
| filter @message like /PRODUCT_METRIC/
| filter event_name = "proposal_accepted" or event_name = "proposal_accepted_without_edit"
| stats count() by event_name
```

```
fields @timestamp, event_name, payload.ms
| filter @message like /PRODUCT_METRIC/ and event_name = "time_to_accept"
| stats avg(payload.ms), pct(payload.ms, 50), pct(payload.ms, 90) by bin(1d)
```

---

## Roadmap (quality)

1. [x] Persist profile (prefs, energy, interests) in DynamoDB; inject into `plan-next-day`.
2. [x] Track energy bands + closed / weekday-closed checks in offline scorers **and** API post-crew `place_quality` filter; trim generated day overages at ≥150% where possible; reviewer crew task (brief-only swaps, no new research tools).
3. [x] Suggest one more place: `suggest_place` crew + `POST /trips/{id}/days/{n}/suggest-place` with `validate_suggested_place` + offline scorer.
3b. [x] Suggest a city (draft candidate): single-agent `suggest_city` crew + `POST /trips/{id}/suggest-city` → `{ candidates }` (default count 1); FE inserts via `addCityStop`; confirm still required. Optional `hint`; server + FE dedupe; FE add gate mirrors `max_cities_for_trip`.
3c. [x] Reorder places (handle-only DnD) + `POST .../places/reorder` + `place_reordered` product event; reorder cities on draft route only.
4. [x] Venue open status via Places enrich when Serper is not enough (BFF: Google Places API New by default; **Amap** for mainland China) before `place_quality`; tool-assisted discovery remains soft.
5. [x] Runtime QualityReport envelope (hard block / soft log) + invocation metadata + POST /events (ADR 004).
6. [x] Offline graded metrics + preference fixtures (heuristic `preference_relevance_score`).
7. [x] Offline graded metric dashboard (`--report`) + LLM-as-judge scorer backend (same metric keys).
8. [x] Persist offline eval runs to dedicated DynamoDB metrics table + private `/metrics` dashboard.
9. [x] Dual-write online QUALITY/PRODUCT metrics to DynamoDB (keep CloudWatch) + Online SPA section.
10. [~] Live `--compare-orchestration` (Nova Pro × `day_plan` vs `day_plan_single`) — partial runs recorded below; **full 31-case decision still open**.
11. [x] Mainland China Places enrich + maps via Amap (高德); researcher Amap tool.

---

## Orchestration experiment (three-agent vs single-call)

**Question:** Does researcher → planner → reviewer beat one structured LLM call enough to justify latency/cost?

| Arm | Crew | Notes |
| --- | --- | --- |
| Multi | `day_plan` | Sequential 3 agents + Serper (+ Amap when China) |
| Single | `day_plan_single` | One agent/task → `DayPlanWithQuality`, same tools/model/schema |

**Decision rule (declared before live runs):** keep three-agent if any of (a) hard-constraint pass rate **+10 pp**, (b) food-only+duplicate+closed **case** failures **−25%** relative (`closed_place_case_rate`), (c) preference relevance **+0.10**, **and** mean `latency_ms` ≤ **2.5×** / `cost_usd` ≤ **3×** single-call. Missing cost on either arm → do **not** keep three-agent (cannot justify spend). Otherwise prefer single-call for MVP.

```bash
cd agent
# Full suite (~31 × 2 arms; ~1h wall-clock) — decision-quality runs
uv run python -m evals --live --compare-orchestration \
  --report reports/orchestration_compare.md

# Fast smoke (~8 cases; both arms in parallel per case)
uv run python -m evals --live --compare-orchestration --orchestration-smoke \
  --report reports/orchestration_compare_smoke.md

# Tool-heavy probe (energy / dense / Amap / closed-day)
uv run python -m evals --live --compare-orchestration \
  --case day_plan_energy_high --case day_plan_kyoto_dense \
  --case day_plan_shanghai_amap --case day_plan_weekday_closed \
  --report reports/orchestration_compare_tooluse.md

# Or pick cases / cap: --case day_plan_seoul --max-cases 4
# Serial arms if needed: --sequential-arms
# optional: --model-id bedrock/...  --runs-dir evals/runs
```

### Learnings (2026-07-25 → 2026-07-26)

#### Correctness (multi vs single)

| Run | Cases | Multi pass | Single pass | Signal | Notes |
| --- | --- | --- | --- | --- | --- |
| Full (`20260725T212347Z`) | 31 | ~90% hard-pass | ~52% hard-pass | **True** (+39 pp) | Early single prompts; many single ValidationErrors |
| Mid (`--max-cases 15`-ish) | 15 | 13/15 | 15/15 | **False** | After single prompt tighten; multi thin-day / dup keys |
| Partial 20 (`20260725T234623Z`) | 20 | 19/20 (95%) | 15/20 (75%) | Preliminary: 3-agent favored (+20 pp) | After porting schema rules into 3-agent; report: [`orchestration_compare_smoke.md`](../agent/reports/orchestration_compare_smoke.md) |
| Tool-heavy (`20260726T001322Z`) | 4 | 4/4 | 4/4 | Preliminary: 3-agent favored (pref +0.25) | Preference-only rule hit; multi had much higher `energy_overage_rate` (0.75 vs 0.25). Not a product lock — [`orchestration_compare_tooluse.md`](../agent/reports/orchestration_compare_tooluse.md) |

**Takeaway:** Single-call can match or beat multi on **schema validity** once prompts are explicit; multi still tends to win on **hard-constraint / preference** when both arms complete. Verdict is **sample-size sensitive** — use full ~31 for a product lock; smoke / tool-heavy / partial runs are **preliminary signals only** (report headline: “final decision pending full repeated evaluation”).

Prompt versions (bump in `agent/models/vacation_planner_models/prompt_meta.py` when agent/task text changes): `day_plan` **2026-07-26.0** (theme prefs + avoid same brand/chain across cities; prior summary includes place names), `day_plan_single` **2026-07-26.0** (same brand framing), `suggest_place` **2026-07-26.3** (same brand framing; BFF also passes `prior_days_summary`). Invocation also records `prompt_hash` of `crew.jsonc` + `agents/*.jsonc`.

#### Cost & latency (Nova Pro, parallel arms)

Observed ballpark (per case, both arms when successful):

| | Multi `day_plan` | Single `day_plan_single` | Ratio |
| --- | --- | --- | --- |
| Mean latency | ~35–40s | ~20–28s | ~1.4–1.8× |
| Cost / case | ~$0.027–0.031 | ~$0.020–0.028 | ~1.1–1.5× |

Both stay well under the decision budgets (2.5× latency / 3× cost). Multi spends more **completion** tokens (3 agents); single often spends more **prompt** tokens (one fat task). Wall-clock for full suite ≈ **1 hour** with parallel arms (2 crews per case).

#### Prompt engineering (transfer single → multi)

What fixed single’s early ValidationError flood, then helped multi’s thin-day / dup-key fails:

1. **Schema-critical category allowlist** — only `museum|food|park|transit|lodging|nightlife|shopping|nature|other`, with remaps (`temple/shrine→other|museum`, `cafe/restaurant→food`). Do **not** teach researchers “category=temple”.
2. **≥2 `category=food` meals** — lunch + dinner as real Places; `reason_to_visit` prefixed `Lunch —` / `Dinner —`.
3. **Unique venue-specific `place_key`** — never generic `shopping` / `lunch` / `dinner` (caused `day_plan_exclusion_museums` fail).
4. **Fill-to-target** — when `target_place_count ≥ 5` or `energy_level ≥ 4`, reviewer/planner must add from the brief instead of shipping a thin 3–4 stop day (`day_plan_energy_high`).

Applied in: `crews/day_plan_single/*` first, then ported into `crews/day_plan` researcher / planner / reviewer + `crew.jsonc` tasks.

#### Nova / Bedrock ToolUse reliability

**Symptom:** `ModelErrorException` / `Model produced invalid sequence as part of ToolUse` (sometimes wrapped in `ConverterError` / `RuntimeError`). Hits tool-heavy cases hardest (`day_plan_energy_high`, dense cities, Amap). Not unique to 3-agent — both arms failed the same case before mitigations.

**Mitigations in `crew_kickoff.py` (and tool modules):**

| Change | Why |
| --- | --- |
| `temperature=0` (+ best-effort `max_tokens=4096`) | AWS: greedy decoding + enough completion tokens; truncation mid-tool-call triggers ToolUse errors |
| Retry **only** ToolUse/ModelError (default `CREW_TOOLUSE_RETRIES=2` → 3 attempts) | Transient Bedrock flake; do not retry schema ValidationErrors |
| Rename tool `Amap Place Search` → `amap_place_search` | Nova is unreliable with spaces/hyphens in tool names |
| Quiet evals: stderr progress, suppress Trace Batch panels | Noise ≠ root cause, but made failures visible |

Env knobs: `CREW_LLM_TEMPERATURE`, `CREW_LLM_MAX_TOKENS`, `CREW_TOOLUSE_RETRIES` (see `agent/.env.example`).

**Evidence:** same energy/dense/Amap/closed slice went from ToolUse producer fails → **8/8 arm passes** after mitigations ([`orchestration_compare_tooluse.md`](../agent/reports/orchestration_compare_tooluse.md)); no retry log line that run → likely first-try success from temp/tokens/name, with retry as safety net.

#### Eval UX notes

- Default: **parallel arms** (2 threads / case). Case-level parallelism not enabled; soft max if added later ≈ 2 cases × 2 arms.
- Reports rewrite live (Progress section); summary table at end. Prefer a **new** `--report` path per experiment so history isn’t overwritten.
- Fair compare = same fixtures on both arms; `--max-cases` is alphabetical — don’t lock MVP from a truncated slice alone.

#### Open decision

MVP still defaults to **`day_plan` (3-agent)** in production until a clean full-suite run post–prompt+Nova fixes is filed. Re-run:

```bash
uv run python -m evals --live --compare-orchestration \
  --report reports/orchestration_compare.md
```

Then update this section + roadmap item 10 with the final keep/simplify call.

---

## Mainland China providers

When destination / overnight is mainland China (not HK/Macau/Taiwan):

- BFF enrich uses **Amap** (`AMAP_WEB_KEY` / `AMAP_WEB_SECRET_ARN`) behind `PlacesClient`; `place_id` stored as `amap:…`
- Place detail: outbound **Amap URI** link (iframe embed is skipped — Amap URI pages are not frameable)
- Researchers get CrewAI tool `custom:amap_place_search` in addition to `SerperDevTool` (`day_plan`, `suggest_place`, `day_plan_single`)

---

## Online metrics (latency / tokens)

`QUALITY_METRIC` events include `latency_ms` (BFF wall clock) and token fields from the crew envelope when CrewAI usage is present. `/metrics` averages only events that carry those fields (`latencySampleSize` / `tokenSampleSize` of the sampled window). Fake crew mode has no tokens by design; redeploy API after emit changes and plan a day to populate latency.
