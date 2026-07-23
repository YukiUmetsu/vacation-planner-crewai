# Environment variables

Canonical reference for **local development** and **Terraform / AWS deploy**. Package READMEs repeat only the vars you need day-to-day; this file is the full map.

Terraform maps many values into Lambda / AgentCore env at apply time — you usually set `TF_VAR_*` (or `terraform.tfvars`), not the runtime names, for deploy.

---

## Quick start: local API + UI (fake crew)

**One command** (DynamoDB Local + API `:8787` + Vite `:5173`):

```bash
./scripts/dev.sh
```

Manual (three terminals) if you prefer:

```bash
# Terminal A — DynamoDB Local
cd backend && docker compose up -d
uv run python scripts/create_local_table.py
# Optional GUI: http://localhost:8001

# Terminal B — API
cd backend
export AUTH_MODE=dev
export CREW_MODE=fake
export SAFETY_MODE=off
export DYNAMODB_ENDPOINT=http://127.0.0.1:8000
export DYNAMODB_TABLE_NAME=vacation-planner-local-table
export AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local AWS_REGION=us-east-1
uv run python scripts/local_api.py

# Terminal C — UI (live mode)
cd frontend
export VITE_USE_DEMO_DATA=false
npm run dev
```

Demo-only UI (no API): leave `VITE_USE_DEMO_DATA` unset and `npm run dev`.

---

## Local development

### Backend (`backend/` — `scripts/local_api.py`, tests, smoke)

| Variable | Typical local | Default (code) | Meaning |
| --- | --- | --- | --- |
| `AUTH_MODE` | **`dev`** (required for local API) | `cognito` | `dev` = trust `X-Dev-User-Sub` / `DEV_USER_SUB`. Deploy uses `cognito`. |
| `CREW_MODE` | `fake` | `fake` | `fake` = no CrewAI. `local` = in-process crews (needs agent deps). `agentcore` = InvokeAgentRuntime (needs ARN). |
| `SAFETY_MODE` | `off` or `keyword` | `keyword` | `keyword` / `bedrock` / `guardrails` / `off`. |
| `BEDROCK_GUARDRAIL_ID` | unset | unset | Required for `SAFETY_MODE=bedrock`. |
| `BEDROCK_GUARDRAIL_VERSION` | unset | `DRAFT` | Guardrail version for ApplyGuardrail. |
| `DYNAMODB_ENDPOINT` | `http://localhost:8000` | unset (AWS) | DynamoDB Local. |
| `DYNAMODB_TABLE_NAME` | `vacation-planner-local-table` | same | Table name. |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | `us-east-1` | `us-east-1` | Region for boto3. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | `local` / `local` | `local` when endpoint set | Dummy creds for DynamoDB Local. |
| `DEV_USER_SUB` | optional | unset | Default user when header missing (smoke scripts). |
| `AGENT_ROOT` | unset | `<repo>/agent` | Root for `CREW_MODE=local`. |
| `AGENT_CREWS_ROOT` | unset | derived | Override crews path for local runner. |
| `AGENT_RUNTIME_ARN` | unset | unset | Required for `CREW_MODE=agentcore`. |
| `GOOGLE_PLACES_API_KEY` | optional | unset | BFF Places enrich before `place_quality`. |
| `PLACES_ENRICH` | `on` | `on` | `off` disables enrich even if key set. |
| `CREW_INPUT_MAX_CHARS` | optional | `16000` | Soft crew-input char budget. |
| `PLAN_NEXT_DAY_ASYNC` | `auto` / `off` | `auto` | `auto` = async only when `CREW_MODE=agentcore`. Local fake stays sync. |
| `LOCAL_API_HOST` | `127.0.0.1` | `127.0.0.1` | Local HTTP bind. |
| `LOCAL_API_PORT` | `8787` | `8787` | Local HTTP port (Vite proxies `/api`). |
| `AWS_LAMBDA_FUNCTION_NAME` | unset locally | set by Lambda | Needed only for async Event self-invoke in AWS. |

### Frontend (`frontend/`)

| Variable | Typical local | Default | Meaning |
| --- | --- | --- | --- |
| `VITE_USE_DEMO_DATA` | unset (demo) or `false` (live) | demo on | `false` = call real API. |
| `VITE_API_URL` | unset (use Vite `/api` proxy) | `/api` | Absolute API base in prod builds (Terraform `api_endpoint`). |
| `VITE_COGNITO_DOMAIN` | unset locally | — | Hosted UI host from `terraform output -raw cognito_hosted_ui_domain` (no `https://`). |
| `VITE_COGNITO_CLIENT_ID` | unset locally | — | `terraform output -raw cognito_user_pool_client_id`. |
| `VITE_COGNITO_REDIRECT_URI` | unset / `http://localhost:5173/callback` | — | Must match Cognito `callback_urls`. |
| `VITE_COGNITO_LOGOUT_URI` | unset / `http://localhost:5173/` | — | Must match Cognito `logout_urls`. |
| `VITE_COGNITO_IDENTITY_PROVIDERS` | unset → `COGNITO` | — | Comma list from `terraform output cognito_identity_providers` (e.g. `COGNITO,Facebook`). |

When Cognito env is set and `VITE_USE_DEMO_DATA=false`, the SPA shows a landing page (Sign in / Sign up / social) until the user completes Hosted UI login. Demo mode stays ungated.

Vite `DEV` builds send `X-Dev-User-Sub: local-dev-user` when **no** Cognito id token is present (local `AUTH_MODE=dev`). When Cognito env is set and you complete Hosted UI login, API calls send `Authorization: Bearer <id_token>` instead.

### Agent / crews (`agent/` — smoke, Phoenix, `CREW_MODE=local`)

Copy [`agent/.env.example`](../agent/.env.example) → `agent/.env` (gitignored).

| Variable | Typical local | Meaning |
| --- | --- | --- |
| `SERPER_API_KEY` | required for real search | SerperDevTool. |
| `AWS_REGION` | e.g. `us-east-1` | Bedrock region. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / profile | your AWS creds | Bedrock invoke. |
| `MODEL` / crew LLM ids | in crew JSONC | Often `bedrock/us.amazon.nova-pro-v1:0` (see agent crews). |
| `CREWAI_DISABLE_TELEMETRY` | `true` (set by scripts) | Disable CrewAI cloud telemetry. |
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:6006/v1/traces` | Local Phoenix traces. |
| `AGENT_ROOT` / `AGENT_CREWS_ROOT` | optional | Path overrides. |

---

## Terraform deploy (`infra/`)

### How to set values

1. **Non-secrets:** `infra/terraform.tfvars` (from [`terraform.tfvars.example`](../infra/terraform.tfvars.example)).
2. **Secrets / account-specific:** shell `export TF_VAR_<name>=...` (preferred so they never hit git).

Terraform automatically reads `TF_VAR_<variable_name>` for each root module variable.

### Root module variables (`infra/variables.tf`)

| Terraform variable | `TF_VAR_…` | Secret? | Notes |
| --- | --- | --- | --- |
| `aws_region` | `TF_VAR_aws_region` | no | Default `us-east-1`. |
| `project_name` | `TF_VAR_project_name` | no | Default `vacation-planner`. |
| `environment` | `TF_VAR_environment` | no | e.g. `dev`. |
| `google_client_id` | `TF_VAR_google_client_id` | no | Cognito Google IdP (optional). |
| `google_client_secret` | `TF_VAR_google_client_secret` | **yes** | Prefer env, not tfvars. |
| `facebook_app_id` | `TF_VAR_facebook_app_id` | no | Cognito Facebook IdP (optional). |
| `facebook_app_secret` | `TF_VAR_facebook_app_secret` | **yes** | Prefer env, not tfvars. |
| `callback_urls` / `logout_urls` | `TF_VAR_callback_urls` (JSON) | no | Include localhost + CloudFront after first deploy. |
| `enable_agentcore` | | no | Must be `true` for API deploy. |
| `agent_runtime_container_uri` | `TF_VAR_agent_runtime_container_uri` | no | ECR image URI from `build_push_image.sh`. |
| `agent_bedrock_models` | | no | Model IDs like `us.amazon.nova-pro-v1:0` (matches crew `llm`). Default in variables.tf. |
| `agent_allowed_bedrock_model_arns` | `TF_VAR_agent_allowed_bedrock_model_arns` | no | Optional full-ARN override; usually leave empty. |
| `serper_api_key` | `TF_VAR_serper_api_key` | **yes** | → AgentCore `SERPER_API_KEY`. |
| `google_places_api_key` | `TF_VAR_google_places_api_key` | **yes** | Optional → API Lambda `GOOGLE_PLACES_API_KEY`. |
| `enable_genai_observability` | | no | Account/region Transaction Search singleton. |
| `genai_observability_indexing_percentage` | | no | e.g. `1` free tier. |
| `enable_bedrock_guardrails` | | no | Create Guardrail module. |
| `safety_mode` | | no | Lambda `SAFETY_MODE` (`keyword` / `bedrock` / …). |
| `bedrock_guardrail_id` / `version` / `arn` | | no | Only if using an external Guardrail. |

### Example deploy exports

```bash
export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export AWS_REGION="${AWS_REGION:-us-east-1}"
# Prefer the URI printed by agent/scripts/build_push_image.sh
# (tag = auto-bumped pyproject version, e.g. .../vacation-planner-agent:0.1.2).
# Avoid :latest — Terraform/AgentCore need a new tag string to roll forward.
export TF_VAR_agent_runtime_container_uri="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/vacation-planner-agent:0.1.2"
export TF_VAR_serper_api_key="..."
export TF_VAR_google_places_api_key="..."   # optional
# export TF_VAR_google_client_secret="..."  # if using Google Hosted UI
# export TF_VAR_facebook_app_id="..."       # if using Facebook Hosted UI
# export TF_VAR_facebook_app_secret="..."
```

Bedrock IAM uses `agent_bedrock_models` in `terraform.tfvars` (default `us.amazon.nova-pro-v1:0`, matching crew `llm` ids). No ARN list or Python export needed.
Also run `backend/scripts/build_lambda.sh` before `terraform apply`.

### Runtime env Terraform injects (do not set these by hand in AWS console)

**API Lambda** (`infra/api`):

| Env | Source |
| --- | --- |
| `DYNAMODB_TABLE_NAME` | DynamoDB module |
| `COGNITO_ISSUER` / `COGNITO_AUDIENCE` | Cognito module |
| `AGENT_RUNTIME_ARN` | AgentCore module |
| `AUTH_MODE` | fixed `cognito` |
| `CREW_MODE` | fixed `agentcore` |
| `SAFETY_MODE` | `var.safety_mode` |
| `LOG_LEVEL` | fixed `INFO` (CloudWatch: filter `API_ERROR`) |
| `BEDROCK_GUARDRAIL_ID` / `BEDROCK_GUARDRAIL_VERSION` | Guardrail outputs / vars |
| `GOOGLE_PLACES_API_KEY` | optional `var.google_places_api_key` |
| `AWS_LAMBDA_FUNCTION_NAME` | AWS runtime (async plan-next-day worker) |

**AgentCore runtime** (`infra/agentcore`):

| Env | Source |
| --- | --- |
| `AWS_REGION` | provider region |
| `SERPER_API_KEY` | `var.serper_api_key` |
| `AGENT_OBSERVABILITY_ENABLED` + `OTEL_*` | when GenAI observability enabled |

---

## Frontend after deploy

```bash
./frontend/scripts/deploy.sh
# Builds with Cognito + API env from terraform outputs (including
# VITE_COGNITO_IDENTITY_PROVIDERS), syncs S3, invalidates CloudFront.
# Ensure CloudFront URLs are in cognito callback_urls / logout_urls before login testing on the CDN.
# Social buttons appear only after TF_VAR_facebook_* / TF_VAR_google_* are applied (Cognito IdPs).
```

---

## Related docs

- Backend day-to-day: [`backend/README.md`](../backend/README.md)
- Infra apply: [`infra/README.md`](../infra/README.md)
- Agent packaging: [`agent/README.md`](../agent/README.md)
- Async plan-next-day: [ADR 001](./architecture-decisions/001-async-plan-next-day-polling.md) (pros/cons: sync vs Event self-invoke vs SQS vs WebSockets)
