# Backend

HTTP API (API Gateway + Lambda): verify Cognito JWT, read/write DynamoDB, invoke AgentCore.

The frontend talks only to this API — never to AgentCore or DynamoDB directly.

## Planned routes

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/trips` | Create trip meta |
| `POST` | `/trips/{id}/propose-cities` | Propose city route |
| `PUT` | `/trips/{id}/cities` | Confirm / edit city route |
| `POST` | `/trips/{id}/plan-next-day` | Plan + persist next day |
| `GET` | `/trips/{id}` | Trip + route + days |
| `GET` | `/trips` | List current user’s trips |

## Layout

```text
src/
  handler.py          # Lambda / HTTP entry
  auth.py             # Cognito JWT verify
  routes/trips.py
  db/                 # single-table helpers + repository
  agentcore/client.py
  services/           # dedupe, trip orchestration
  models/             # Pydantic (align with docs/DATA_MODEL.md)
scripts/
  create_local_table.py
tests/
docker-compose.yml    # DynamoDB Local
```

## Local DynamoDB

Two layers:

1. **moto** (in pytest) — no Docker; CI-friendly access-pattern tests
2. **DynamoDB Local** (Docker) — manual exploration against a real Local endpoint

### Unit / access-pattern tests (moto)

```bash
cd backend
uv sync --group dev
uv run pytest
```

### DynamoDB Local (manual)

Data is stored in a Docker volume (`dynamodb_data`), so tables survive `docker compose restart` / container recreate. `docker compose down -v` deletes that volume.

```bash
cd backend
docker compose up -d
uv run python scripts/create_local_table.py
```

Default endpoint: `http://localhost:8000`  
Default table: `vacation-planner-local-table`

Point the backend at Local with:

```bash
export DYNAMODB_ENDPOINT=http://localhost:8000
export DYNAMODB_TABLE_NAME=vacation-planner-local-table
export AWS_ACCESS_KEY_ID=local
export AWS_SECRET_ACCESS_KEY=local
export AWS_REGION=us-east-1
```

Stop Local (`-v` also wipes persisted data):

```bash
docker compose down      # keep volume
docker compose down -v  # delete volume
```

Schema matches `infra/dynamodb` (pk/sk + gsi1). See `docs/DATA_MODEL.md`.

Scaffold only — not deployed yet.
