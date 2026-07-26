# Orchestration compare

run_id: `20260725T212347Z`
cases: 31

## Decision

- keep_three_agent: **True**
- hard_constraint_pass_rate +38.7 pp (≥ 10.0)
- food_only+duplicate+closed relative drop 42% (≥ 25%)

## Aggregates

### day_plan

passed=28 failed=3

```
metric                             value
-------------------------------------------
closed_place_case_rate             0.0645
closed_place_rate                  0.0145
completion_tokens                  3797.6774
cost                               0.0288
cost_usd                           0.0288
duplicate_rate                     0.0000
energy_overage_rate                0.1935
explicit_exclusion_violation_rate  0.0000
food_only_day_rate                 0.0000
grounding_rate                     1.0000
hard_constraint_pass               0.9032
hard_constraint_pass_rate          0.9032
latency_ms                         72319.6452
missing_meals_rate                 0.0000
non_food_place_count               2.5484
preference_relevance_score         0.8710
prompt_tokens                      20761.9355
schema_valid                       0.9032
schema_valid_rate                  0.9032
total_tokens                       24559.6129
wrong_city_rate                    0.0000
```

### day_plan_single

passed=16 failed=15

```
metric                             value
-------------------------------------------
closed_place_case_rate             0.0000
closed_place_rate                  0.0000
completion_tokens                  2682.0000
cost                               0.0295
cost_usd                           0.0295
duplicate_rate                     0.0556
energy_overage_rate                0.1667
explicit_exclusion_violation_rate  0.0000
food_only_day_rate                 0.0556
grounding_rate                     1.0000
hard_constraint_pass               0.5161
hard_constraint_pass_rate          0.5161
latency_ms                         40716.0056
missing_meals_rate                 0.0000
non_food_place_count               1.9444
preference_relevance_score         0.8889
prompt_tokens                      26171.5556
schema_valid                       0.5161
schema_valid_rate                  0.5161
total_tokens                       28853.5556
wrong_city_rate                    0.0000
```

### day_plan sample failures

- day_plan_paris_culture: places[0] ("Musée d'Orsay") is permanently closed
- day_plan_seoul: places[0] ('Gyeongbokgung Palace') is permanently closed
- day_plan_shanghai_amap: places[2] ('Shanghai Museum') is closed on weekday 2 for date 2026-09-02

### day_plan_single sample failures

- day_plan_avoid_visited: producer error: ValidationError: 1 validation error for DayPlanWithQuality
day_plan
  Value error, DayPlan must include lunch and dinner as category=food stops (got 1 food place(s)) [type=value_error, input_value={'day_index': 1, 'date': ..
- day_plan_bangkok: producer error: ValidationError: 3 validation errors for DayPlanWithQuality
day_plan.places.0.category
  Input should be 'museum', 'food', 'park', 'transit', 'lodging', 'nightlife', 'shopping', 'nature' or 'other' [type=enum, input_value='t
- day_plan_day2_context: producer error: ValidationError: 2 validation errors for DayPlanWithQuality
day_plan.places.0.category
  Input should be 'museum', 'food', 'park', 'transit', 'lodging', 'nightlife', 'shopping', 'nature' or 'other' [type=enum, input_value='t
