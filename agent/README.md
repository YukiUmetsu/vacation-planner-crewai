# Agent (AgentCore + CrewAI)

CrewAI crews packaged for **Amazon Bedrock AgentCore Runtime**.

## Layout

| Path | Purpose |
| --- | --- |
| `crews/day_plan/` | Active crew: research → itinerary (local + runtime) |
| `crews/city_route/` | Placeholder: propose cities for country destinations |
| `models/` | Shared Pydantic shapes (`Place`, `DayPlan`, `CityRoute`, …) |
| `main.py` | AgentCore entrypoint (stub) |
| `tests/` | Agent/crew tests |

## Local run (day plan crew)

```bash
cd crews/day_plan
uv sync
# Terminal 1: uv run python -m phoenix.server.main serve
uv run python run_with_phoenix.py --topic "Tokyo"
```

Or:

```bash
cd crews/day_plan
CREWAI_DMN=1 uv run crewai run --inputs '{"topic":"Tokyo"}'
```

Phoenix UI: http://localhost:6006 → project **`vacation_planner`**.

## Deploy note

Ship `main.py` + crews + models to AgentCore. Do **not** include Phoenix or `run_with_phoenix.py` in the runtime image.
