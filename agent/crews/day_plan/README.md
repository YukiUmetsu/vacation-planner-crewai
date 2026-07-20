# Day plan crew

Plans **one day** at a time. Final task output is structured `DayPlan` via
`"output_pydantic": { "python": "models.DayPlan" }` (local re-export of `vacation_planner_models`).

## Agents

| Agent | Role |
| --- | --- |
| `day_plan_researcher` | Serper research for places in `overnight_city` |
| `day_plan_planner` | Assemble `DayPlan` (`output_pydantic`) |

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
