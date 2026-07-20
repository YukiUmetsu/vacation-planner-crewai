# Agent (AgentCore + CrewAI)

CrewAI crews packaged for **Amazon Bedrock AgentCore Runtime**.

## Layout

| Path | Purpose |
| --- | --- |
| `crews/day_plan/` | Active crew: research → itinerary (local + runtime) |
| `crews/city_route/` | Placeholder: propose cities for country destinations |
| `models/` | Installable package `vacation_planner_models` (Pydantic + `place_key`) |
| `main.py` | AgentCore entrypoint (stub) |
| `tests/` | Model/crew unit tests |

### Shared models

`models/` is the package **`vacation-planner-models`**. Import as `vacation_planner_models`. Crews pull it in via editable uv path, e.g. day_plan:

```toml
vacation-planner-models = { path = "../../models", editable = true }
```

Later task wiring:

```jsonc
"output_pydantic": { "python": "vacation_planner_models.DayPlan" }
```

```bash
cd models && uv sync --extra dev && uv run pytest ../tests
```

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
