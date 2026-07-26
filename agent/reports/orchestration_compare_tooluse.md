# Orchestration compare

run_id: `20260726T001322Z`
cases: 4
parallel_arms: `True`

## Summary

**Preliminary signal:** three-agent favored; final decision pending full repeated evaluation.

_Pre-declared rule outcome on this sample (`n=4`): `keep_three_agent=True` — not a product lock._

| Check | Multi (`day_plan`) | Single (`day_plan_single`) | Result |
| --- | --- | --- | --- |
| Pass / fail | **4/4** pass (0 fail) | **4/4** pass (0 fail) | — |
| Hard-constraint pass | **100%** | **100%** | **+0 pp** |
| Schema valid | 100% | 100% | — |
| Preference relevance | 0.88 | 0.62 | — |
| Mean latency | 37s | 20s | 1.83× |
| Cost / case | $0.031 | $0.020 | 1.52× |

### Decision reasons

- preference_relevance_score +0.25 (≥ 0.1)

**Caveat:** multi-agent `energy_overage_rate` was **0.75** vs **0.25** on single-call — preference gain on four cases does not outweigh that load risk until a full repeated suite confirms.

## Progress

- Orchestration compare run_id=20260726T001322Z cases=4 (parallel arms; 8 crew runs)
- [1/4] day_plan_energy_high …
-   day_plan: PASS (35.6s)
-   day_plan_single: PASS (25.9s)
- [2/4] day_plan_kyoto_dense …
-   day_plan: PASS (40.2s)
-   day_plan_single: PASS (19.8s)
- [3/4] day_plan_shanghai_amap …
-   day_plan: PASS (30.6s)
-   day_plan_single: PASS (18.9s)
- [4/4] day_plan_weekday_closed …
-   day_plan: PASS (40.5s)
-   day_plan_single: PASS (15.7s)
-   → day_plan: passed=4 failed=0
-   → day_plan_single: passed=4 failed=0

## Detailed aggregates

### day_plan

passed=4 failed=0

```
metric                             value
-------------------------------------------
closed_place_case_rate             0.0000
closed_place_rate                  0.0000
completion_tokens                  4024.2500
cost                               0.0306
cost_usd                           0.0306
duplicate_rate                     0.0000
energy_overage_rate                0.7500
explicit_exclusion_violation_rate  0.0000
food_only_day_rate                 0.0000
grounding_rate                     1.0000
hard_constraint_pass               1.0000
hard_constraint_pass_rate          1.0000
latency_ms                         36740.0000
missing_meals_rate                 0.0000
non_food_place_count               3.0000
preference_relevance_score         0.8750
prompt_tokens                      22200.7500
schema_valid                       1.0000
schema_valid_rate                  1.0000
total_tokens                       26225.0000
wrong_city_rate                    0.0000
```

### day_plan_single

passed=4 failed=0

```
metric                             value
-------------------------------------------
closed_place_case_rate             0.0000
closed_place_rate                  0.0000
completion_tokens                  2038.0000
cost                               0.0201
cost_usd                           0.0201
duplicate_rate                     0.0000
energy_overage_rate                0.0000
explicit_exclusion_violation_rate  0.0000
food_only_day_rate                 0.0000
grounding_rate                     1.0000
hard_constraint_pass               1.0000
hard_constraint_pass_rate          1.0000
latency_ms                         20059.2500
missing_meals_rate                 0.0000
non_food_place_count               2.5000
preference_relevance_score         0.6250
prompt_tokens                      16993.2500
schema_valid                       1.0000
schema_valid_rate                  1.0000
total_tokens                       19031.2500
wrong_city_rate                    0.0000
```
