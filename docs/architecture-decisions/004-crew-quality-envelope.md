# ADR 004: Crew quality envelope and hard vs soft relevance

## Status

Accepted (MVP)

## Context

Day plans could pass schema and feasibility gates while still being a poor match
for traveler preferences. We need structured relevance signals and versioned
invocation metadata without stuffing scores into persisted Dynamo DAY items.

## Decision

1. Agent crews return a **CrewEnvelope**: `{ result, quality?, invocation }`.
2. Persisted Dynamo items remain domain-only (`DayPlan` / route / place).
3. Reviewer emits `DayPlanWithQuality` (`day_plan` + `QualityReport`).
4. **Hard** failure tags block the plan (`duplicate_place`, `wrong_city`,
   `closed_place`, `excluded_category`, `food_only_day`).
   **Soft** tags (`preference_mismatch`, `too_far`, `weak_reason`,
   `ungrounded_place`, `weak_day_balance`, `too_packed`, `energy_overload`,
   `missing_meals`) are logged and do not block persistence once BFF gates
   finish. **Energy:** soft tag above comfort; generated day plans at ≥150%
   of comfort are auto-trimmed by dropping optional tail stops when possible
   (meals / required non-food protected). Suggest-place append never removes
   existing stops. See [`PLANNING_QUALITY.md`](../PLANNING_QUALITY.md).
5. BFF merges crew quality with deterministic gate outcomes and emits
   `QUALITY_METRIC` / `PRODUCT_METRIC` log lines for CloudWatch
   (`energy_places_trimmed` when auto-trim dropped stops).
6. Offline evals expose graded metric rates; LLM-as-judge is a later swap-in
   for the same metric keys. Energy overage is metric-only offline
   (`energy_overage_rate`), not a hard scorer failure.

## Consequences

- AgentCore and local runners must stay envelope-compatible; bare DayPlan is
  still accepted for one release via unwrap.
- Prompt/model experiments can be compared via `prompt_version`, `prompt_hash`,
  `model_id`, and `git_sha` on quality logs.
- Product acceptance rates start as `POST /events` allowlisted client events.
