# Day plan crew

Plans **one day** at a time. Final task output is structured `DayPlan` from the
**reviewer** via `"output_pydantic": { "python": "day_models.DayPlan" }` (local re-export of `vacation_planner_models`; unique module name avoids clashing with `city_models`).

## Agents

| Agent | Role |
| --- | --- |
| `day_plan_researcher` | Serper research for places in `overnight_city` |
| `day_plan_planner` | Draft `DayPlan` |
| `day_plan_reviewer` | No tools — revise draft using the research brief only (swap dubious/closed stops; keep 3–6) |

Traveler context inputs: `preferences`, `interests`, `energy_level`, `max_comfortable_minutes`, `already_visited`.

The API also applies hard post-crew filters for permanently closed / weekday-closed places and energy load (`place_quality`).

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
