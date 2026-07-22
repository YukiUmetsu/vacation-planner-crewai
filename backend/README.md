# Backend

HTTP API (API Gateway + Lambda): Cognito JWT (via API Gateway authorizer + `sub` claims), DynamoDB, and crew invocation (`fake` locally / AgentCore in AWS).

The frontend talks only to this API — never to AgentCore or DynamoDB directly.

## Routes

Implemented and covered by moto tests. **Local use requires `AUTH_MODE=dev`.** Deployed Lambda uses `AUTH_MODE=cognito` and expects API Gateway JWT claims (`requestContext.authorizer.jwt.claims.sub`).

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/trips` | Create trip meta (city destinations auto-confirm a synthetic route) |
| `POST` | `/trips/{id}/propose-cities` | Propose city route via crew |
| `PUT` | `/trips/{id}/cities` | Confirm / edit city route |
| `POST` | `/trips/{id}/plan-next-day` | Plan + persist next day (dedupe places) |
| `GET` | `/trips/{id}` | Trip + route + days |
| `GET` | `/trips` | List current user’s trips |

## Layout

```text
src/
  handler.py          # Lambda / HTTP entry
  auth.py             # AUTH_MODE=dev | cognito (APIGW JWT claims)
  http_utils.py
  routes/trips.py
  crews/              # CrewRunner: fake (default) | local | agentcore
  db/
  services/
  models/api.py
scripts/
  build_lambda.sh     # package src + deps for Terraform zip
  create_local_table.py
  smoke_trip_flow.py
tests/
docker-compose.yml
```

## Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `AUTH_MODE` | `cognito` | **Fail closed.** Local: set `dev` (`X-Dev-User-Sub` / `DEV_USER_SUB`). Deploy: `cognito` reads `sub` from API Gateway JWT authorizer claims |
| `CREW_MODE` | `fake` (code default) | Local/tests: `fake` (no CrewAI). `local` = CrewAI in-process (needs `agent/crews`). Deployed Lambda (Terraform): **`agentcore`** = InvokeAgentRuntime |
| `SAFETY_MODE` | `keyword` | `keyword` deny-list; `bedrock` / `guardrails` → ApplyGuardrail (needs `BEDROCK_GUARDRAIL_ID`); `off` disables |
| `BEDROCK_GUARDRAIL_ID` | unset | Required when `SAFETY_MODE=bedrock` |
| `BEDROCK_GUARDRAIL_VERSION` | `DRAFT` | Guardrail version for ApplyGuardrail |
| `DYNAMODB_ENDPOINT` | unset | Set to `http://localhost:8000` for DynamoDB Local |
| `DYNAMODB_TABLE_NAME` | `vacation-planner-local-table` | Table name |
| `AGENT_ROOT` | `<repo>/agent` | Used by `CREW_MODE=local` only |

## Local API (:8787)

Thin stdlib adapter maps HTTP → API Gateway–shaped events → [`handler.handler`](./src/handler.py). Vite proxies `/api` here; the adapter strips the `/api` prefix.

```bash
cd backend
uv sync --group dev
export AUTH_MODE=dev CREW_MODE=fake SAFETY_MODE=off
# Optional: DynamoDB Local (docker compose up -d + create_local_table.py)
uv run python scripts/local_api.py
# curl -s -H 'x-dev-user-sub: local-dev-user' http://127.0.0.1:8787/api/trips
```

`AUTH_MODE` must be `dev` or the process exits (fail closed).

Trip smoke against DynamoDB Local:

```bash
docker compose up -d
uv run python scripts/create_local_table.py
export DYNAMODB_ENDPOINT=http://localhost:8000
export DYNAMODB_TABLE_NAME=vacation-planner-local-table
export AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local AWS_REGION=us-east-1
export AUTH_MODE=dev CREW_MODE=fake SAFETY_MODE=off
uv run python scripts/smoke_trip_flow.py
```

Real CrewAI from the backend process (`CREW_MODE=local`) is optional and **not** how Lambda runs. Prefer crew smoke tests under `agent/crews/*`, or wait for AgentCore.

## Lambda package (required before `terraform apply`)

Terraform zips `backend/.build/lambda` (source **plus** production deps such as pydantic). Build first:

```bash
cd backend
./scripts/build_lambda.sh
```

Then from `infra/`: `terraform plan` / `apply`. The zip does **not** include CrewAI; Terraform sets Lambda `CREW_MODE=agentcore` (production). Use `CREW_MODE=fake` only for local/backend-only work.

## Tests (moto)

```bash
cd backend
uv sync --group dev
uv run pytest
```

These offline tests also run on `git push` via [`.githooks/pre-push`](../.githooks/pre-push). Install once:

```bash
./scripts/install-git-hooks.sh
```

`plan-next-day` claims the day slot with a conditional `next_day_index` update, then writes the DAY only if absent (conflict → 409 + claim rollback). Duplicate-only crew output returns 422 without saving.

Schema matches `infra/dynamodb` (pk/sk + gsi1). See `docs/DATA_MODEL.md`.
