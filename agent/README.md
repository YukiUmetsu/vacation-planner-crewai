# Agent (AgentCore + CrewAI)

CrewAI crews packaged for **Amazon Bedrock AgentCore Runtime**.

## Layout

| Path | Purpose |
| --- | --- |
| `crews/day_plan/` | Day crew: research → `DayPlan` (structured, one day) |
| `crews/city_route/` | City route crew: research → `CityRoute` (structured) |
| `models/` | Installable package `vacation_planner_models` (Pydantic + `place_key`) |
| `main.py` | AgentCore Runtime entrypoint (`BedrockAgentCoreApp`) |
| `pyproject.toml` | Runtime deps including `bedrock-agentcore` |
| `tests/` | Model/crew unit tests |

### Shared models

`models/` is the package **`vacation-planner-models`**. Import as `vacation_planner_models`. Crews pull it in via editable uv path, e.g. day_plan:

```toml
vacation-planner-models = { path = "../../models", editable = true }
```

Later task wiring uses a **uniquely named** local re-export (CrewAI resolves under the crew root). Names differ so both crews can load in one process:

```jsonc
"output_pydantic": { "python": "day_models.DayPlan" }
// city_route: "city_models.CityRoute"
```

(`day_models.py` / `city_models.py` re-export `vacation_planner_models`.)

```bash
cd models && uv sync --extra dev && uv run pytest ../tests
```

## Local run (day plan crew)

```bash
cd crews/day_plan
uv sync
# Secrets: agent/.env (shared)
# Terminal 1: uv run python -m phoenix.server.main serve
uv run python smoke_test.py --overnight-city Tokyo --day-index 1 --date 2026-09-01
# or: uv run python run_with_phoenix.py --overnight-city Tokyo --day-index 1 --date 2026-09-01
```

Or:

```bash
cd crews/day_plan
CREWAI_DMN=1 uv run crewai run --inputs '{"topic":"Tokyo"}'
```

Phoenix UI: http://localhost:6006 → project **`vacation_planner`**.

## Runtime entrypoint (AgentCore)

From `agent/` (not a crew subdirectory):

```bash
cd agent
uv sync
uv run python -c "from bedrock_agentcore import BedrockAgentCoreApp; print('ok')"
# Local smoke of the entrypoint (needs AWS/model creds for a real kickoff):
# uv run python main.py
```

`CREW_MODE=agentcore` on the BFF expects Lambda env **`AGENT_RUNTIME_ARN`** (set by Terraform when AgentCore is enabled), matching `backend/src/agentcore/client.py`.

## Runtime packaging

`crew_kickoff.py` loads `crews/<name>/crew.jsonc` relative to this package root (`Path(__file__).parent / "crews"`). The wheel therefore includes:

- `main.py`, `crew_kickoff.py`, `invoke_payload.py`
- `crews/day_plan/` and `crews/city_route/` runtime assets (`crew.jsonc`, `*_models.py`, `agents/`, `tools/`, `knowledge/`, `skills/`)

Shared Pydantic models install via the **`vacation-planner-models`** dependency (`models/`). Local-only files are **not** packaged: `.venv/`, `logs/`, `uv.lock`, `run_with_phoenix.py`, `smoke_test.py`, crew `pyproject.toml` / README.

Container / AgentCore image options that both work:

1. **Install the wheel** from this `pyproject.toml` so crews land next to `crew_kickoff.py`.
2. **Docker image** from [`Dockerfile`](./Dockerfile) (copies the same runtime assets; see [`.dockerignore`](./.dockerignore)).

```bash
cd agent
uv build && unzip -l dist/*.whl | grep crew.jsonc
docker build -t vacation-planner-agent:latest .
```

Do **not** install only the three Python modules without `crews/` — `run_crew` will raise `crew_not_found`.

## Offline evals

Harness scaffolding lives in [`evals/`](./evals/). Implement scorers + goldens yourself (see `evals/README.md`).
