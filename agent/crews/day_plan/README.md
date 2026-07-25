# Day plan crew

Plans **one day** at a time. Planner drafts `DayPlan`; reviewer emits
`DayPlanWithQuality` via `"output_pydantic": { "python": "day_models.DayPlanWithQuality" }`
(local re-export of `vacation_planner_models`; unique module name avoids clashing with `city_models`).

## Agents

| Agent | Role |
| --- | --- |
| `day_plan_researcher` | Serper + `custom:amap_place_search` (prefer Amap for mainland China) |
| `day_plan_planner` | Draft `DayPlan` |
| `day_plan_reviewer` | No tools — revise draft using the research brief only; emit `DayPlanWithQuality` |

Traveler context inputs: `preferences`, `interests`, `energy_level`, `max_comfortable_minutes`, `target_place_count`, `already_visited`, `food_crawl_mode`, `min_non_food_places`, `day_shape_hint`.

The API also applies hard post-crew filters for permanently closed / weekday-closed places, energy load, meal stops, and day balance (`place_quality` / `day_balance`). Place-count target is soft (prompt); schema hard range stays 3–7. BFF Places enrich uses Google by default and **Amap** when overnight/destination is mainland China.

For a same-model single-call baseline used in evals, see [`../day_plan_single/`](../day_plan_single/).

## Setup

```bash
# once, under agent/
cp .env.example .env

cd crews/day_plan
uv sync
```

## Smoke test

```bash
uv run python smoke_test.py \
  --overnight-city Tokyo \
  --day-index 1 \
  --date 2026-09-01
```

## Run with Phoenix

```bash
# Terminal 1 (from this dir or city_route)
uv run python -m phoenix.server.main serve

# Terminal 2
uv run python run_with_phoenix.py \
  --overnight-city Tokyo \
  --day-index 1 \
  --date 2026-09-01 \
  --preferences "culture, food, moderate pace" \
  --already-visited ""
```

Phoenix: http://localhost:6006 → project **`vacation_planner`**.
