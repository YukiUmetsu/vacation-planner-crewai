# City route crew

Final task output is structured `CityRoute` via `"output_pydantic": { "python": "models.CityRoute" }` (local re-export of `vacation_planner_models`; CrewAI requires the class under the crew project root).


## Agents

| Agent | Role |
| --- | --- |
| `city_route_researcher` | Serper research (cities, nights, logistics) |
| `city_route_planner` | Assemble `CityRoute` (`output_pydantic`) |

## Setup

```bash
# once, under agent/
cp .env.example .env   # SERPER_API_KEY, AWS_REGION

cd crews/city_route
uv sync
```

## Run with Phoenix

```bash
# Terminal 1
uv run python -m phoenix.server.main serve

# Terminal 2
uv run python run_with_phoenix.py \
  --origin "San Francisco" \
  --destination Japan \
  --destination-type country \
  --start-date 2026-09-01 \
  --end-date 2026-09-10 \
  --preferences "culture, food, moderate pace"
```

Or:

```bash
CREWAI_DMN=1 uv run crewai run
```

Phoenix: http://localhost:6006 → project **`vacation_planner`**.
