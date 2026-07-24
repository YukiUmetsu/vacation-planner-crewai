# Backend

HTTP API (API Gateway + Lambda): Cognito JWT (via API Gateway authorizer + `sub` claims), DynamoDB, and crew invocation (`fake` locally / AgentCore in AWS).

The frontend talks only to this API — never to AgentCore or DynamoDB directly.

## Routes

**Contract:** [`openapi.yaml`](./openapi.yaml) (OpenAPI 3.1) — full path/method list, request/response schemas, and `GET /places/photo` (`refresh` bypass). Drift-checked by `tests/test_openapi.py`.

Implemented and covered by moto tests. **Local use requires `AUTH_MODE=dev`.** Deployed Lambda uses `AUTH_MODE=cognito` and expects API Gateway JWT claims (`requestContext.authorizer.jwt.claims.sub`).

Local Vite proxies `/api/*` and strips the prefix; OpenAPI paths match Lambda/API Gateway (`/trips`, not `/api/trips`).

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/trips` | Create trip meta (city destinations auto-confirm a synthetic route) |
| `POST` | `/trips/{id}/propose-cities` | Propose city route via crew |
| `PUT` | `/trips/{id}/cities` | Confirm / edit city route |
| `POST` | `/trips/{id}/plan-next-day` | Plan + persist next day (dedupe places) |
| `GET` | `/trips/{id}` | Trip + route + days |
| `GET` | `/trips` | List current user’s trips |
| `GET` | `/profile` | Load user profile (defaults if missing) |
| `PUT` | `/profile` | Upsert prefs, energy_level, interests, visited_places |
| `GET` | `/places/photo` | Resolve owned-trip place photo (`refresh=1` bypasses cache) |
| `POST` | `/events` | Product analytics event |
| `GET` | `/admin/metrics/*` | Eval / online metrics (admin allowlist) |

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

Full map (local + Terraform `TF_VAR_*` + injected Lambda/AgentCore env): **[`docs/ENVIRONMENT.md`](../docs/ENVIRONMENT.md)**.

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
| `AGENT_RUNTIME_ARN` | unset | Required for `CREW_MODE=agentcore` |
| `CREW_INPUT_MAX_CHARS` | `16000` | Soft budget for crew `inputs` (char proxy). Over budget → slim advisory fields only; full visited list still used for BFF dedupe |
| `GOOGLE_PLACES_API_KEY` | unset | Optional Places API (New) enrich before `place_quality` |
| `PLACES_ENRICH` | `on` | `off` disables enrich even if a key is set |
| `PLAN_NEXT_DAY_ASYNC` | `auto` | `auto` = async 202 when `CREW_MODE=agentcore`; `on`/`off` force async or sync |

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

### Finding API errors in CloudWatch (prod)

Log group: **`/aws/lambda/vacation-planner-dev-api`** (replace `dev` with your `environment`).

Do **not** use the vague console “Search all log groups” box — open that log group → **Logs Insights** (last 1–3 hours):

```
fields @timestamp, @message, @requestId
| filter @message like /API_ERROR/
| sort @timestamp desc
| limit 50
```

5xx only:

```
fields @timestamp, @message
| filter @message like /API_ERROR/ and @message like /status=5/
| sort @timestamp desc
| limit 50
```

DELETE trip failures:

```
fields @timestamp, @message
| filter @message like /API_ERROR/ and @message like /method=DELETE/ and @message like /\/trips\//
| sort @timestamp desc
| limit 20
```

CLI equivalent:

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/vacation-planner-dev-api \
  --start-time $(($(date +%s)*1000 - 3600000)) \
  --filter-pattern 'API_ERROR'
```

Every API error emits `API_ERROR …` plus `API_ERROR_JSON {…}` (status, code, method, path, request_id). Match the browser’s `x-amzn-requestid` / Lambda request id to `@requestId`.

After `terraform apply`, open the free-tier dashboard: CloudWatch → Dashboards → `vacation-planner-dev-api-logs` (or `terraform output api_logs_dashboard_name`).

| Dashboard signal | Meaning |
| --- | --- |
| **LambdaErrors** (`[ERROR]`) | Usually **5xx** `API_ERROR` / unhandled exceptions (DynamoDB IAM, worker crash, etc.). |
| **LambdaWarnings** (`[WARNING]`) | Usually **4xx** ApiErrors, or soft fails (Places enrich, secrets, AgentCore client). |
| **AWS/Lambda Errors / Throttles** | Platform invoke failures / concurrency limits (not the same as app `[ERROR]` lines). |
| **AgentCore Invocations / Errors / SystemErrors / UserErrors / Throttles / Latency** | Built-in runtime health (`AWS/Bedrock-AgentCore`). SystemErrors ≈ service-side; UserErrors ≈ bad client input. |

App-level crew failures also log `crew_failed` in `/aws/bedrock-agentcore/runtimes/<runtime_id>-DEFAULT`. Deeper agent traces: CloudWatch GenAI Observability.

### Places open-status enrich (optional)

After the crew returns places, the BFF can call **Google Places API (New)** Text Search to overwrite `operational_status` / `closed_weekdays` / `open_hours` before `place_quality` filters. Soft behavior:

| Env | Effect |
| --- | --- |
| `GOOGLE_PLACES_API_KEY` unset | No HTTP calls; keep crew fields |
| `PLACES_ENRICH=off` | Force skip even if a key is set |
| Key set + enrich on | Lookup by name + address/city; hits must match name **and** location (overnight city or address tokens) before status overwrite; API errors leave the place unchanged |

Terraform: `TF_VAR_google_places_api_key` → Lambda env (same pattern as AgentCore `SERPER_API_KEY`). Enable **Places API (New)** on the Google Cloud project that owns the key.

**API key restrictions (required if you set a key):**

1. Application restriction: prefer **IP addresses** of the API Lambda NAT/egress (or leave unset only for local experiments).
2. API restriction: allow **only** Places API (New) — not Maps JS, Geocoding, etc.
3. Do not commit the key; pass via `TF_VAR_…` / local env only.

**Secret storage note:** Terraform `sensitive = true` only redacts CLI output. The value still lands in Terraform state and Lambda environment configuration (same as Serper today). Prefer **Secrets Manager / SSM SecureString** + IAM read for production hardening; this MVP keeps env injection for parity with Serper.

Schema matches `infra/dynamodb` (pk/sk + gsi1). See `docs/DATA_MODEL.md`.
