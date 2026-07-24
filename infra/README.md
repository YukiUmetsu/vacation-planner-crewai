# Infrastructure (Terraform)

Provisions the AWS stack for Vacation Planner:

| Module | Resources |
| --- | --- |
| `dynamodb/` | Single-table `${project}-${env}-table` (`pk`/`sk`, GSI1, TTL on `expires_at`) + metrics table |
| `secrets/` | Secrets Manager shells (values via CLI / ephemeral pepper write-only) |
| `cognito/` | User pool, app client, Hosted UI; social IdPs synced from SM (not TF state) |
| `api/` | Lambda (from `backend/.build/lambda` — run `backend/scripts/build_lambda.sh` first) + HTTP API + Cognito JWT authorizer |
| `frontend/` | S3 + CloudFront (OAC) for the SPA |
| `agentcore/` | Bedrock AgentCore runtime (required for API deploy; needs ECR image) |
| `guardrails/` | Bedrock Guardrail + published version (content, topics, words, PII) |

Schema details: [`docs/DATA_MODEL.md`](../docs/DATA_MODEL.md).

**Environment / secrets reference:** [`docs/ENVIRONMENT.md`](../docs/ENVIRONMENT.md).

## Prerequisites

- Terraform `>= 1.11` (ephemeral + `secret_string_wo`)
- AWS credentials with permission to create the resources above
- AWS provider `>= 6.17` (AgentCore resources)
- Optional: Google and/or Facebook OAuth apps for Hosted UI social login (credentials in Secrets Manager)
- ECR image of the agent for AgentCore

## Quick start

```bash
# 1) Build the Lambda artifact (src + production Python deps)
../backend/scripts/build_lambda.sh

cd infra   # if not already here
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars (callback URLs, agent_runtime_container_uri via TF_VAR)

terraform init
./scripts/validate.sh   # SPA↔Gateway HTTP methods + terraform validate
terraform plan
terraform apply

# 2) Seed Secrets Manager (once / on rotate), then sync Cognito IdPs
#    see docs/ENVIRONMENT.md for put-secret-value examples
./scripts/sync_cognito_idps_from_secrets.sh
```

The API Lambda package is **`backend/.build/lambda`**, not raw `backend/src`. Skipping the build step makes `terraform plan` fail or ship a broken zip (missing pydantic, etc.).

**Secrets stay out of Terraform state:** OAuth / Serper / Places are never set as `TF_VAR_*` for routine applies. Cognito IdP `client_secret` is applied by the sync script (AWS provider has no `client_secret_wo` yet). Lambda and AgentCore receive **secret ARNs** only and call `GetSecretValue` at runtime.
Useful outputs after apply:

- `api_endpoint` → frontend `VITE_API_URL`
- `cognito_user_pool_id` / `cognito_user_pool_client_id` / `cognito_hosted_ui_domain`
- `frontend_site_url` / `frontend_bucket_name` → upload `frontend` build
- `agent_runtime_arn` → AgentCore runtime ARN

### Deploy frontend assets

Preferred (reads Terraform outputs, builds with Cognito/API env, syncs S3, invalidates CloudFront):

```bash
../frontend/scripts/deploy.sh
```

Then Hosted UI login works on CloudFront: Cognito callback/logout URLs always include `frontend_site_url` (merged in root `main.tf`), so omitting CloudFront from tfvars cannot wipe it on the next apply.

### Configure AgentCore

1. Build and push an agent container to ECR (see [`agent/Dockerfile`](../agent/Dockerfile) and packaging notes in [`agent/README.md`](../agent/README.md)).
2. Set `enable_agentcore = true` and `agent_bedrock_models` in `terraform.tfvars` (defaults to Nova Pro to match crew `llm` ids). Prefer env vars for account-specific / secret values:

```bash
export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
# Use the tag printed by ../agent/scripts/build_push_image.sh
# (auto-bumped version, e.g. .../vacation-planner-agent:0.1.2), not :latest.
export TF_VAR_agent_runtime_container_uri="${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/vacation-planner-agent:0.1.2"
# Serper / Places: put-secret-value into vacation-planner-dev/serper and …/google-places
```

In `terraform.tfvars`:

```hcl
agent_bedrock_models = ["us.amazon.nova-pro-v1:0"]
```

Terraform expands those IDs to the inference-profile + foundation-model ARNs IAM needs. You do **not** need to export a JSON ARN list.

Cross-region inference profiles (`us.*`, …) also get an intentional `bedrock:*::foundation-model/<id>` ARN (region wildcard, **model id still exact**). That is required because the profile may invoke the FM outside this stack’s region; it is not a blanket `bedrock:*` grant.
3. `terraform apply`

Lambda always uses `CREW_MODE=agentcore`. Apply fails if the AgentCore runtime ARN is empty.

`AWS_ACCOUNT_ID` is not sensitive; using it from the shell just avoids committing account-specific values. Seed Serper/Places into Secrets Manager (see ENVIRONMENT.md); Lambda/AgentCore read via secret ARNs at runtime.

Product-metrics pepper is bootstrapped into Secrets Manager with ephemeral `random_password` + `secret_string_wo` (value not stored in Terraform state). To preserve an old pepper after migration, `put-secret-value` that string into `${project}-${env}/product-metrics-pepper` and set `bootstrap_product_metrics_pepper = false` on the secrets module if needed.

**Google Places key restrictions:** restrict the key to Places API (New) only, and prefer IP restriction to Lambda egress.
**HTTP methods / CORS:** JWT routes and API Gateway `cors_configuration.allow_methods` share `local.api_http_methods` in [`api/main.tf`](./api/main.tf). When the SPA adds a verb (e.g. `DELETE`), add it there. Before apply (or after infra / FE API client changes), run [`scripts/validate.sh`](./scripts/validate.sh) — it checks SPA↔Gateway method drift then `terraform validate`.

**Ops dashboard (free tier):** Terraform creates **2** custom metrics (`LambdaErrors` = log lines with `[ERROR]`, typically 5xx / Tracebacks; `LambdaWarnings` = `[WARNING]`, typically 4xx ApiErrors + soft failures like Places/secrets) plus **1** dashboard `${project}-${env}-api-logs`. The same dashboard also charts **built-in** (non-custom) metrics: Lambda `Errors`/`Throttles`/`Duration`, and AgentCore `Invocations` / `Errors` / `SystemErrors` / `UserErrors` / `Throttles` / `Latency` / `Duration` under `AWS/Bedrock-AgentCore`. After apply: CloudWatch → Dashboards → that name (or `terraform output api_logs_dashboard_name`). For agent traces/sessions use GenAI Observability; for app crashes search agent logs for `crew_failed`.

## Least privilege model

IAM policies are intentionally scoped to the resources created or configured by this stack:

| Principal | Allowed access |
| --- | --- |
| Backend Lambda role | DynamoDB trip table: `GetItem`/`PutItem`/`UpdateItem`/`DeleteItem`/`Query` (+ indexes); metrics table: `GetItem`/`PutItem`/`Query`; log streams; AgentCore invoke; optional ApplyGuardrail; `secretsmanager:GetSecretValue` on Places + product-metrics pepper ARNs. |
| AgentCore runtime role | ECR pull for configured repo; AgentCore logs; `logs:PutResourcePolicy` (unified traces, when GenAI observability is on); optional X-Ray/CW metrics; Bedrock models from allow-list; `secretsmanager:GetSecretValue` on Serper ARN. |
| CloudFront service principal | Reads objects from only the generated frontend bucket, constrained by the distribution `AWS:SourceArn`. |

### Bedrock Guardrails

`enable_bedrock_guardrails` (default `true`) creates a high-safety Guardrail:

- Content filters at **HIGH** (hate, insults, sexual, violence, misconduct) + **PROMPT_ATTACK** on input
- Denied topics: weapons/violence, self-harm, adult sexual content, illegal activity
- Word policy: profanity managed list + prompt-injection phrases
- PII: block on input, anonymize on output for contact/financial types (email, phone, SSN, cards, bank, password — not NAME/ADDRESS, which false-positive on travel text)
- Publishes an immutable version (`skip_destroy = true`)

Lambda env gets `BEDROCK_GUARDRAIL_ID` / `BEDROCK_GUARDRAIL_VERSION` from the module. Set `safety_mode = "bedrock"` (or `"guardrails"`) to call ApplyGuardrail from the API Lambda; Terraform requires a non-empty Guardrail ID + ARN in that case (provided automatically when `enable_bedrock_guardrails = true`). Default remains `keyword` for cheaper local-style denylist behavior in AWS until you opt in.

When using an external Guardrail (`enable_bedrock_guardrails = false`), set `bedrock_guardrail_id`, `bedrock_guardrail_version`, and `bedrock_guardrail_arn` so Lambda env and ApplyGuardrail IAM both match.

AgentCore is **required for AWS deploy** (`enable_agentcore` defaults to `true`). The API Lambda precondition requires a non-empty runtime ARN; there is no deployed `CREW_MODE=fake` path. When AgentCore is enabled, `agent_runtime_container_uri` must be set and `agent_bedrock_models` (or an ARN override) must expand to a non-empty allow-list so IAM never grants `bedrock:*`. If the crew switches models, update `agent_bedrock_models` to match.

The AgentCore log permissions use the AWS-documented runtime log group prefix `/aws/bedrock-agentcore/runtimes/*` because the concrete runtime/endpoint log group name is assigned by AgentCore after creation.

### GenAI Observability (OpenTelemetry)

Everything required for **CloudWatch → GenAI Observability → Bedrock AgentCore** is Terraform-managed when `enable_genai_observability = true` (default). That flag also gates AgentCore ADOT env + X-Ray IAM.

| Layer | What Terraform configures |
| --- | --- |
| Account/region (`observability/`) | CloudWatch Logs resource policy (`VacationPlannerTransactionSearchXRay`) for X-Ray → `aws/spans`, `/aws/application-signals/data`, `/aws/bedrock-agentcore/runtimes/*`; `awscc_xray_transaction_search_config` (indexing %, default **1** = free tier). |
| AgentCore runtime | Only when observability is enabled: ADOT env (`AGENT_OBSERVABILITY_ENABLED=true`, distro/configurator, `UNIFIED_TRACES_DESTINATION_ENABLED`, `service.name`, `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=NO_CONTENT`); IAM: X-Ray put/sampling, `cloudwatch:PutMetricData` (`bedrock-agentcore`), `logs:PutResourcePolicy` on this runtime’s log groups (unified traces → per-agent log group); CloudWatch Logs **TRACES → XRAY** delivery (GenAI Agents View) |
| Agent image | Neutral by default (`entrypoint.sh`). ADOT (`opentelemetry-instrument`) runs only when AgentCore sets `AGENT_OBSERVABILITY_ENABLED=true`. |

**Account singleton:** Transaction Search is one config per account+region. Keep `enable_genai_observability = true` in **only one** stack (e.g. `dev`). Other envs should set it `false` (or share this stack’s state).

**If GenAI Observability Agents View shows 0 data:**

1. Confirm Transaction Search is `CloudWatchLogs` / `ACTIVE` (`aws xray get-trace-segment-destination`).
2. Apply with observability on — AgentCore needs **TRACES → XRAY** delivery (in `agentcore/main.tf`). ADOT rows in `aws/spans` alone often are not enough for Agents View.
   - Deployer IAM needs `logs:PutDeliverySource`, `logs:PutDeliveryDestination`, `logs:CreateDelivery` (and matching `Describe*`/`Delete*` for destroy). `AccessDeniedException` on the delivery destination usually means those are missing.
3. Raise `genai_observability_indexing_percentage` (default **1** = free tier; low traffic often indexes **zero** traces). While debugging, use `100`, invoke once, wait ~10 minutes.
4. Widen the GenAI console time range to cover recent invokes (`AWS/Bedrock-AgentCore` Invocations).
5. Proof spans exist: Logs Insights on `aws/spans` → `filter @message like /gen_ai_agent/`.
6. After apply, confirm delivery exists: `aws logs describe-delivery-sources` should list `${project}-${env}-agent-traces` with `logType=TRACES`.

**Already enabled?** Import before apply:

```bash
terraform import 'module.observability.awscc_xray_transaction_search_config.this[0]' "$(aws sts get-caller-identity --query Account --output text)"
terraform import 'module.observability.aws_cloudwatch_log_resource_policy.transaction_search[0]' VacationPlannerTransactionSearchXRay
```

After apply, wait ~10 minutes, invoke a crew, then open GenAI Observability. Spans from invocations **before** enable are not indexed.

## Layout

```text
infra/
  main.tf / variables.tf / outputs.tf / versions.tf / providers.tf
  terraform.tfvars.example
  dynamodb/
  cognito/
  api/           # zips backend/.build/lambda → Lambda (run build_lambda.sh first)
  frontend/
  agentcore/
  observability/ # Transaction Search + X-Ray → CloudWatch Logs (GenAI Observability)
  guardrails/    # Bedrock Guardrail + version
```

## Notes

- Trip API routes are implemented in `backend/src`. Redeploy after `./scripts/build_lambda.sh` so the zip picks up code changes.
- Lambda `CREW_MODE` is always **`agentcore`** in AWS. Apply fails without a runtime ARN (`enable_agentcore=true` + ECR image + model ARNs). Local work uses `CREW_MODE=fake` outside Terraform.
- Google / Facebook IdPs are listed when `enable_google_idp` / `enable_facebook_idp` are true; credentials are synced from Secrets Manager (`./scripts/sync_cognito_idps_from_secrets.sh`), not Terraform.
- After apply, `terraform output cognito_identity_providers` lists enabled IdPs for `VITE_COGNITO_IDENTITY_PROVIDERS` (set automatically by `frontend/scripts/deploy.sh`).
- **Facebook `attributes required: [email]`:** Cognito requires email. In Meta Developer Console → App → **App Review → Permissions and features**, grant **Advanced Access** for `email` (and `public_profile`). Use a Facebook account that has a primary email and accept the email permission on the consent screen. Then `terraform apply` so Cognito IdP scopes are `public_profile, email`.
- Do not commit `terraform.tfvars`, `.terraform/`, or `*.tfstate*`.
