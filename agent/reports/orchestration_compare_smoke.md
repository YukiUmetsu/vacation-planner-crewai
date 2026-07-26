# Orchestration compare

run_id: `20260725T234623Z`
cases: 20
parallel_arms: `True`

## Summary

**Preliminary signal:** three-agent favored; final decision pending full repeated evaluation.

_Pre-declared rule outcome on this sample (`n=20`): `keep_three_agent=True` — not a product lock._

| Check | Multi (`day_plan`) | Single (`day_plan_single`) | Result |
| --- | --- | --- | --- |
| Pass / fail | **19/20** pass (1 fail) | **15/20** pass (5 fail) | — |
| Hard-constraint pass | **95%** | **75%** | **+20 pp** |
| Schema valid | 95% | 75% | — |
| Preference relevance | 0.84 | 0.80 | — |
| Mean latency | 40s | 28s | 1.42× |
| Cost / case | $0.030 | $0.028 | 1.09× |

### Decision reasons

- hard_constraint_pass_rate +20.0 pp (≥ 10.0)

## Progress

- Orchestration compare run_id=20260725T234623Z cases=20 (parallel arms; 40 crew runs)
- [1/20] day_plan_avoid_visited …
-   day_plan: PASS (37.7s)
-   day_plan_single: FAIL (29.8s)
- [2/20] day_plan_balance_food_forward …
-   day_plan: PASS (49.7s)
-   day_plan_single: PASS (17.9s)
- [3/20] day_plan_balance_food_only …
-   day_plan: PASS (36.3s)
-   day_plan_single: PASS (25.9s)
- [4/20] day_plan_bangkok …
-   day_plan: PASS (36.5s)
-   day_plan_single: PASS (34.9s)
- [5/20] day_plan_barcelona_food …
-   day_plan: PASS (39.4s)
-   day_plan_single: PASS (31.4s)
- [6/20] day_plan_beijing_amap …
-   day_plan: PASS (37.5s)
-   day_plan_single: PASS (21.3s)
- [7/20] day_plan_day2_context …
-   day_plan: PASS (42.1s)
-   day_plan_single: PASS (20.1s)
- [8/20] day_plan_energy_2 …
-   day_plan: PASS (29.8s)
-   day_plan_single: PASS (18.5s)
- [9/20] day_plan_energy_high …
-   day_plan: FAIL (108.6s)
-   day_plan_single: FAIL (67.8s)
- [10/20] day_plan_energy_low …
-   day_plan: PASS (25.6s)
-   day_plan_single: PASS (16.4s)
- [11/20] day_plan_example_shape …
-   day_plan: PASS (36.8s)
-   day_plan_single: PASS (10.7s)
- [12/20] day_plan_exclusion_museums …
-   day_plan: PASS (35.9s)
-   day_plan_single: PASS (13.1s)
- [13/20] day_plan_food_crawl_ok …
-   day_plan: PASS (34.6s)
-   day_plan_single: FAIL (16.7s)
- [14/20] day_plan_food_forward_balanced …
-   day_plan: PASS (36.2s)
-   day_plan_single: PASS (42.9s)
- [15/20] day_plan_hong_kong_google …
-   day_plan: PASS (30.3s)
-   day_plan_single: PASS (19.6s)
- [16/20] day_plan_include_breakfast …
-   day_plan: PASS (38.3s)
-   day_plan_single: PASS (17.2s)
- [17/20] day_plan_kyoto_dense …
-   day_plan: PASS (42.9s)
-   day_plan_single: PASS (20.2s)
- [18/20] day_plan_multi_visited …
-   day_plan: PASS (31.4s)
-   day_plan_single: FAIL (23.5s)
- [19/20] day_plan_no_nightlife …
-   day_plan: PASS (35.7s)
-   day_plan_single: FAIL (74.0s)
- [20/20] day_plan_osaka_street_food …
-   day_plan: PASS (29.2s)
-   day_plan_single: PASS (35.4s)
-   → day_plan: passed=19 failed=1
-   → day_plan_single: passed=15 failed=5

## Detailed aggregates

### day_plan

passed=19 failed=1

```
metric                             value
-------------------------------------------
closed_place_case_rate             0.0000
closed_place_rate                  0.0000
completion_tokens                  3809.1053
cost                               0.0302
cost_usd                           0.0302
duplicate_rate                     0.0000
energy_overage_rate                0.4211
explicit_exclusion_violation_rate  0.0000
food_only_day_rate                 0.0526
grounding_rate                     1.0000
hard_constraint_pass               0.9500
hard_constraint_pass_rate          0.9500
latency_ms                         39707.7377
missing_meals_rate                 0.0000
non_food_place_count               2.4211
preference_relevance_score         0.8421
prompt_tokens                      22474.1579
schema_valid                       0.9500
schema_valid_rate                  0.9500
total_tokens                       26283.2632
wrong_city_rate                    0.0000
```

### day_plan_single

passed=15 failed=5

```
metric                             value
-------------------------------------------
closed_place_case_rate             0.0000
closed_place_rate                  0.0000
completion_tokens                  2243.9412
cost                               0.0277
cost_usd                           0.0277
duplicate_rate                     0.0000
energy_overage_rate                0.3529
explicit_exclusion_violation_rate  0.0588
food_only_day_rate                 0.0000
grounding_rate                     1.0000
hard_constraint_pass               0.7500
hard_constraint_pass_rate          0.7500
latency_ms                         27866.8590
missing_meals_rate                 0.0000
non_food_place_count               2.1765
preference_relevance_score         0.8039
prompt_tokens                      25638.4118
schema_valid                       0.7500
schema_valid_rate                  0.7500
total_tokens                       27882.3529
wrong_city_rate                    0.0000
```

### day_plan sample failures

- day_plan_energy_high: producer error: RuntimeError: Model error: Model produced invalid sequence as part of ToolUse. Please refer to the model tool use troubleshooting guide.

### day_plan_single sample failures

- day_plan_avoid_visited: places[0] ('Gotokuji Temple') is closed on weekday 2 for date 2026-09-02
- day_plan_energy_high: producer error: ConverterError: Failed to convert text into a Pydantic model due to error: Model error: Model produced invalid sequence as part of ToolUse. Please refer to the model tool use troubleshooting guide.
- day_plan_food_crawl_ok: producer error: ValidationError: 1 validation error for DayPlanWithQuality
day_plan.places
  List should have at least 3 items after validation, not 2 [type=too_short, input_value=[{'place_id': 'GinzaHachi...tes_from_previous': 30}], input_
