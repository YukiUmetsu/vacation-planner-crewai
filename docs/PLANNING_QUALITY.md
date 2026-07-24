# Planning quality, safety, and evals

Canonical product rules for how we judge a day’s plan. Package READMEs hold implementation detail; this doc is the shared contract.

## Doc map (safety / guardrails / evals)

| Topic | Where |
| --- | --- |
| **Traveler energy ↔ day load** | This file (canonical thresholds) |
| **Input safety (prompt injection / harmful prefs)** | [`backend/README.md`](../backend/README.md) (`SAFETY_MODE`), [`backend/src/services/bedrock_safety.py`](../backend/src/services/bedrock_safety.py) |
| **Bedrock Guardrail policies + IAM** | [`infra/README.md`](../infra/README.md) (Guardrails section), [`infra/guardrails/`](../infra/guardrails/) |
| **Offline crew evals** | [`agent/evals/README.md`](../agent/evals/README.md) |
| **AgentCore trust boundary** | [ADR 003](./architecture-decisions/003-bff-agentcore-runtime-only.md) |

---

## Energy level → warning thresholds

Traveler **energy level** is an integer **1–5** (signal bars in the profile UI).

**What we measure:** total planned minutes for one day =

- sum of place `estimated_minutes` (activity), plus  
- sum of `travel_minutes_from_previous` between stops (travel).

Canonical minute table (keep in sync):

- Frontend: `frontend/src/lib/energyLevel.ts` (`MAX_COMFORTABLE_TOTAL_MINUTES`)
- Backend: `backend/src/services/energy.py`
- Offline scorers: `agent/evals/scorers.py`

### Warning thresholds (canonical)

| Energy | Meaning (short) | Warn after (activity + travel) | Minutes |
| --- | --- | --- | ---: |
| **1** | Very low — limited mobility / long rests | **4.5 hours** | 270 |
| **2** | Low — short days, frequent breaks | **6.5 hours** | 390 |
| **3** | Moderate — average adult day (default) | **8.5 hours** | 510 |
| **4** | High — long active days | **12 hours** | 720 |
| **5** | Very high — packed itineraries OK | **14 hours** | 840 |

### Soft vs hard enforcement

| Layer | Behavior |
| --- | --- |
| **Frontend** | Soft banner via `assessDayEnergyLoad` (`ok` / `caution` / `overloaded`) |
| **Crew prompts** | `energy_level` + `max_comfortable_minutes` / `remaining_minutes` in day_plan + suggest_place |
| **API hard gate** | `place_quality.filter_quality_places` (plan-next-day) and `validate_suggested_place` (suggest-place) reject over-budget days |
| **Offline evals** | Scorers fail when day/suggestion exceeds the threshold |

### Severity bands (UI)

Let `ratio = totalMinutes / comfortMaxMinutes`.

| Band | Condition | UI |
| --- | --- | --- |
| `ok` | `ratio ≤ 1` | No warning |
| `caution` | `1 < ratio ≤ 1.2` | Soft “a bit packed” message |
| `overloaded` | `ratio > 1.2` | Stronger “too full” message |

Example: energy **3** → warn after **510** min. Day with **540** min → caution. Day with **620** min → overloaded.

---

## Related hard checks (today)

| Check | Layer |
| --- | --- |
| Dedupe places across days (`place_key`) | Backend `dedupe_places` + crew `already_visited` prompt |
| Crew input size (token proxy) | BFF `crew_context_budget.slim_crew_inputs` — only when over `CREW_INPUT_MAX_CHARS`; cut order: `already_visited` → `prior_days_summary` → `city_route_json` → `preferences`. Full visited list still used for dedupe / quality. Large context fields (`already_visited`, `preferences`, `interests`) are interpolated once in the research task; later tasks remind without re-listing. |
| Place count 3–6 / schema | Agent `DayPlan` Pydantic + eval scorers |
| Permanently closed / weekday-closed | Crew reviewer + **Google Places BFF enrich** + `place_quality` + scorers |
| Energy budget | Crew prompts + `place_quality` / `validate_suggested_place` + scorers |
| Lunch + dinner food stops | Crew prompts + `DayPlan` Pydantic (≥2 `category=food`) + BFF `require_meal_stops` (energy trim preserves food) + scorers |
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
| **1. Deterministic BFF** | Dedupe, Places enrich, closed/weekday, energy, meal stops (`place_quality` / `require_meal_stops`) | Yes (existing `ApiError` codes) |
| **2. Reviewer `QualityReport`** | Scores + `failure_tags` on CrewEnvelope; soft preference fit | Hard tags only (see table below) |
| **3. Offline / online metrics** | Eval `metrics` aggregates; `QUALITY_METRIC` / `PRODUCT_METRIC` logs | No (observe only) |

Persisted Dynamo DAY items stay **domain-only** — quality/invocation are never written. See [ADR 004](./architecture-decisions/004-crew-quality-envelope.md).

### Hard vs soft failure tags

| Tag | Class | MVP behavior |
| --- | --- | --- |
| `duplicate_place`, `wrong_city`, `closed_place`, `too_packed`, `energy_overload`, `excluded_category`, `missing_meals` | **Hard** | Fail / regenerate; log `QUALITY_METRIC` |
| `preference_mismatch`, `too_far`, `weak_reason`, `ungrounded_place` | **Soft** | Log only; still persist if hard gates pass |

### Metric catalog

**Runtime (`QUALITY_METRIC` JSON line)** — dimensions/fields: `trip_id`, `day_index`, `passes_relevance`, `relevance_score`, `constraint_score`, `failure_tags`, `guardrail_code`, `places_count`, plus invocation `crew_name`, `prompt_version`, `prompt_hash`, `model_id`, `git_sha`, `input_context_chars`, `context_was_slimmed`, `output_schema_version`.

Useful rates (derive in Logs Insights): empty/dedupe/closed/energy/meals/safety/context-truncation from `guardrail_code` + tag counts.

**Offline evals (`EvalResult.metrics`)** — per case then mean via `aggregate_metrics`:

| Key | Meaning |
| --- | --- |
| `schema_valid` / `schema_valid_rate` | Binary scorer pass |
| `hard_constraint_pass` / `_rate` | Same as schema for MVP |
| `preference_relevance_score` | Interest/keyword overlap (0–1) |
| `explicit_exclusion_violation_rate` | `already_visited` or `excluded_categories` hit |
| `duplicate_rate`, `closed_place_rate`, `energy_overage_rate`, `grounding_rate` | Structural rates |
| `latency_ms`, `cost` | Reserved (live / Bedrock usage later) |

Preference fixtures: `day_plan_preference_food`, `day_plan_preference_exclusion`, `day_plan_preference_mismatch`.

**Phase 2.1 — LLM-as-judge:** same metric keys; swap the scorer backend for `preference_relevance_score` only (documented hook; not implemented).

**Online product (`PRODUCT_METRIC` via `POST /events`)** — allowlisted names: `proposal_accepted`, `proposal_accepted_without_edit`, `manual_edit`, `time_to_accept` (payload `ms`), `plan_regenerated`, `place_deleted`, `suggestion_accepted`, `place_reordered` (reserved until reorder UX). No PII; `user_sub_hash` is peppered SHA-256.

### CloudWatch Logs Insights (examples)

```
fields @timestamp, trip_id, day_index, failure_tags, guardrail_code, prompt_version
| filter @message like /QUALITY_METRIC/
| sort @timestamp desc
| limit 50
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
2. [x] Enforce energy caps + closed / weekday-closed checks in offline scorers **and** API post-crew `place_quality` filter; reviewer crew task (brief-only swaps, no new research tools).
3. [x] Suggest one more place: `suggest_place` crew + `POST /trips/{id}/days/{n}/suggest-place` with `validate_suggested_place` + offline scorer.
4. [x] Venue open status via Places API when Serper is not enough (BFF enrich with Google Places API New before `place_quality`; tool-assisted discovery remains soft).
5. [x] Runtime QualityReport envelope (hard block / soft log) + invocation metadata + POST /events (ADR 004).
6. [x] Offline graded metrics + preference fixtures (heuristic `preference_relevance_score`).
7. [ ] Offline graded metric dashboards + LLM-as-judge scorer backend (same metric keys).
