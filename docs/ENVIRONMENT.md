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
export DYNAMODB_METRICS_TABLE_NAME=vacation-planner-local-metrics
export METRICS_ADMIN_SUBS=local-dev-user
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
| `DYNAMODB_TABLE_NAME` | `vacation-planner-local-table` | same | Trip single-table name. |
| `DYNAMODB_METRICS_TABLE_NAME` | `vacation-planner-local-metrics` | same | Dedicated offline-eval metrics table. |
| `METRICS_ADMIN_SUBS` | `local-dev-user` (via `dev.sh`) | unset | Comma-separated Cognito (or dev) subs for `GET /admin/metrics`. Empty → 403 for everyone. Online quality/product also dual-write to the metrics table (soft-fail). |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | `us-east-1` | `us-east-1` | Region for boto3. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | `local` / `local` | `local` when endpoint set | Dummy creds for DynamoDB Local. |
| `DEV_USER_SUB` | optional | unset | Default user when header missing (smoke scripts). |
| `AGENT_ROOT` | unset | `<repo>/agent` | Root for `CREW_MODE=local`. |
| `AGENT_CREWS_ROOT` | unset | derived | Override crews path for local runner. |
| `AGENT_RUNTIME_ARN` | unset | unset | Required for `CREW_MODE=agentcore`. |
| `GOOGLE_PLACES_API_KEY` | optional | unset | Local plaintext override. |
| `GOOGLE_PLACES_SECRET_ARN` | optional | unset | Prod: SM ARN; BFF Places enrich before `place_quality`. |
| `PRODUCT_METRICS_HASH_PEPPER` | optional | code fallback (local only) | Local plaintext override. |
| `PRODUCT_METRICS_PEPPER_SECRET_ARN` | optional | unset | Prod: SM ARN for `user_sub` hashes. |
| `BACKEND_GIT_SHA` | optional | unset | Attached to `QUALITY_METRIC` logs when set (deploy/CI). |
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
| `SERPER_API_KEY` | required for real search (local) | SerperDevTool. |
| `SERPER_SECRET_ARN` | AgentCore | Runtime loads key into `SERPER_API_KEY` if unset. |
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
2. **Secrets:** AWS Secrets Manager (not `TF_VAR_*`, not Terraform state). Terraform creates secret *shells*; you `put-secret-value`, then sync Cognito IdPs.
3. **Account-specific non-secret:** e.g. `TF_VAR_agent_runtime_container_uri`.

Requires Terraform **>= 1.11** (ephemeral / `secret_string_wo` for product-metrics pepper bootstrap).

### Secrets Manager (no secrets in Terraform state)

| Secret name | Shape | Consumer |
| --- | --- | --- |
| `${project}-${env}/cognito/google` | JSON `{client_id, client_secret}` | Cognito Google IdP via [`infra/scripts/sync_cognito_idps_from_secrets.sh`](../infra/scripts/sync_cognito_idps_from_secrets.sh) |
| `${project}-${env}/cognito/facebook` | JSON `{app_id, app_secret}` | Cognito Facebook IdP via same script |
| `${project}-${env}/serper` | plain string (or JSON with `api_key`) | AgentCore runtime (`SERPER_SECRET_ARN`) |
| `${project}-${env}/google-places` | plain string | API Lambda (`GOOGLE_PLACES_SECRET_ARN`) |
| `${project}-${env}/product-metrics-pepper` | plain string | API Lambda (`PRODUCT_METRICS_PEPPER_SECRET_ARN`); TF bootstraps via ephemeral + `secret_string_wo` |

```bash
# After first apply creates the shells:
aws secretsmanager put-secret-value \
  --secret-id vacation-planner-dev/cognito/google \
  --secret-string '{"client_id":"...","client_secret":"..."}'
aws secretsmanager put-secret-value \
  --secret-id vacation-planner-dev/cognito/facebook \
  --secret-string '{"app_id":"...","app_secret":"..."}'
aws secretsmanager put-secret-value \
  --secret-id vacation-planner-dev/serper \
  --secret-string 'YOUR_SERPER_KEY'
aws secretsmanager put-secret-value \
  --secret-id vacation-planner-dev/google-places \
  --secret-string 'YOUR_PLACES_KEY'

cd infra && ./scripts/sync_cognito_idps_from_secrets.sh
```

Local/dev can still set plaintext `GOOGLE_PLACES_API_KEY`, `PRODUCT_METRICS_HASH_PEPPER`, or `SERPER_API_KEY` (preferred over SM when set).

### Root module variables (`infra/variables.tf`)

| Terraform variable | `TF_VAR_…` | Secret? | Notes |
| --- | --- | --- | --- |
| `aws_region` | `TF_VAR_aws_region` | no | Default `us-east-1`. |
| `project_name` | `TF_VAR_project_name` | no | Default `vacation-planner`. |
| `environment` | `TF_VAR_environment` | no | e.g. `dev`. |
| `enable_google_idp` | | no | List Google on the app client (default `true`). Credentials via SM + sync script. |
| `enable_facebook_idp` | | no | List Facebook on the app client (default `true`). |
| `callback_urls` / `logout_urls` | `TF_VAR_callback_urls` (JSON) | no | Extras only (default localhost). **CloudFront for this stack is always merged in** from `module.frontend.site_url`. |
| `enable_agentcore` | | no | Must be `true` for API deploy. |
| `agent_runtime_container_uri` | `TF_VAR_agent_runtime_container_uri` | no | ECR image URI from `build_push_image.sh`. |
| `agent_bedrock_models` | | no | Model IDs like `us.amazon.nova-pro-v1:0` (matches crew `llm`). Default in variables.tf. |
| `agent_allowed_bedrock_model_arns` | `TF_VAR_agent_allowed_bedrock_model_arns` | no | Optional full-ARN override; usually leave empty. |
| `metrics_admin_subs` | `TF_VAR_metrics_admin_subs` | no | Comma-separated Cognito subs → `METRICS_ADMIN_SUBS` for `/admin/metrics` + `/metrics` SPA. Empty → 403 for all. |
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
```

Bedrock IAM uses `agent_bedrock_models` in `terraform.tfvars` (default `us.amazon.nova-pro-v1:0`, matching crew `llm` ids). No ARN list or Python export needed.
Also run `backend/scripts/build_lambda.sh` before `terraform apply`, then `./scripts/sync_cognito_idps_from_secrets.sh` after secrets are seeded.

### Runtime env Terraform injects (do not set these by hand in AWS console)

**API Lambda** (`infra/api`):

| Env | Source |
| --- | --- |
| `DYNAMODB_TABLE_NAME` | DynamoDB module (trip single-table) |
| `DYNAMODB_METRICS_TABLE_NAME` | DynamoDB module (eval metrics table) |
| `COGNITO_ISSUER` / `COGNITO_AUDIENCE` | Cognito module |
| `AGENT_RUNTIME_ARN` | AgentCore module |
| `AUTH_MODE` | fixed `cognito` |
| `CREW_MODE` | fixed `agentcore` |
| `SAFETY_MODE` | `var.safety_mode` |
| `LOG_LEVEL` | fixed `INFO` | CloudWatch log group `/aws/lambda/${project}-${env}-api`. Search with filter `API_ERROR` (see backend README). |
| `BEDROCK_GUARDRAIL_ID` / `BEDROCK_GUARDRAIL_VERSION` | Guardrail outputs / vars |
| `GOOGLE_PLACES_SECRET_ARN` | secrets module (runtime fetch) |
| `PRODUCT_METRICS_PEPPER_SECRET_ARN` | secrets module (runtime fetch) |
| `METRICS_ADMIN_SUBS` | `var.metrics_admin_subs` |
| `AWS_LAMBDA_FUNCTION_NAME` | AWS runtime (async plan-next-day worker) |

**AgentCore runtime** (`infra/agentcore`):

| Env | Source |
| --- | --- |
| `AWS_REGION` | provider region |
| `SERPER_SECRET_ARN` | secrets module (runtime fetch → `SERPER_API_KEY`) |
| `AGENT_OBSERVABILITY_ENABLED` + `OTEL_*` | when GenAI observability enabled |

---

## Frontend after deploy

```bash
./frontend/scripts/deploy.sh
# Builds with Cognito + API env from terraform outputs (including
# VITE_COGNITO_IDENTITY_PROVIDERS), syncs S3, invalidates CloudFront.
# CloudFront callback/logout URLs are merged automatically in infra/main.tf —
# if CDN login fails with a redirect_mismatch, run terraform apply so Cognito
# picks up the current frontend_site_url.
# Social IdPs: seed SM + ./infra/scripts/sync_cognito_idps_from_secrets.sh.
```

---

## Related docs

- Backend day-to-day: [`backend/README.md`](../backend/README.md)
- Infra apply: [`infra/README.md`](../infra/README.md)
- Agent packaging: [`agent/README.md`](../agent/README.md)
- Async plan-next-day: [ADR 001](./architecture-decisions/001-async-plan-next-day-polling.md) (pros/cons: sync vs Event self-invoke vs SQS vs WebSockets)
