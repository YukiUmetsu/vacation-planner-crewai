# Infrastructure (Terraform)

Provisions the AWS stack for Vacation Planner:

| Module | Resources |
| --- | --- |
| `dynamodb/` | Single-table `${project}-${env}-table` (`pk`/`sk`, GSI1, TTL on `expires_at`) |
| `cognito/` | User pool, app client, Hosted UI domain; optional Google / Facebook IdPs |
| `api/` | Lambda (from `backend/.build/lambda` — run `backend/scripts/build_lambda.sh` first) + HTTP API + Cognito JWT authorizer |
| `frontend/` | S3 + CloudFront (OAC) for the SPA |
| `agentcore/` | Bedrock AgentCore runtime (required for API deploy; needs ECR image) |
| `guardrails/` | Bedrock Guardrail + published version (content, topics, words, PII) |

Schema details: [`docs/DATA_MODEL.md`](../docs/DATA_MODEL.md).

**Environment / `TF_VAR_*` reference:** [`docs/ENVIRONMENT.md`](../docs/ENVIRONMENT.md).

## Prerequisites

- Terraform `>= 1.5`
- AWS credentials with permission to create the resources above
- AWS provider `>= 6.17` (AgentCore resources)
- Optional: Google and/or Facebook OAuth apps for Hosted UI social login
- ECR image of the agent for AgentCore

## Quick start

```bash
# 1) Build the Lambda artifact (src + production Python deps)
../backend/scripts/build_lambda.sh

cd infra   # if not already here
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars (and/or export TF_VAR_google_client_secret, TF_VAR_serper_api_key)

terraform init
terraform plan
terraform apply
```

The API Lambda package is **`backend/.build/lambda`**, not raw `backend/src`. Skipping the build step makes `terraform plan` fail or ship a broken zip (missing pydantic, etc.).

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

Then add the CloudFront URL to `callback_urls` / `logout_urls` and `terraform apply` again (the script warns if those URLs are missing).

### Configure AgentCore

1. Build and push an agent container to ECR (see [`agent/Dockerfile`](../agent/Dockerfile) and packaging notes in [`agent/README.md`](../agent/README.md)).
2. Set `enable_agentcore = true` and `agent_bedrock_models` in `terraform.tfvars` (defaults to Nova Pro to match crew `llm` ids). Prefer env vars for account-specific / secret values:

```bash
export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
# Use the tag printed by ../agent/scripts/build_push_image.sh
# (auto-bumped version, e.g. .../vacation-planner-agent:0.1.2), not :latest.
export TF_VAR_agent_runtime_container_uri="${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/vacation-planner-agent:0.1.2"
export TF_VAR_serper_api_key="REPLACE_WITH_SERPER_API_KEY"
export TF_VAR_google_places_api_key="REPLACE_WITH_GOOGLE_PLACES_API_KEY"  # optional; BFF open-status enrich
```

In `terraform.tfvars`:

```hcl
agent_bedrock_models = ["us.amazon.nova-pro-v1:0"]
```

Terraform expands those IDs to the inference-profile + foundation-model ARNs IAM needs. You do **not** need to export a JSON ARN list.

Cross-region inference profiles (`us.*`, …) also get an intentional `bedrock:*::foundation-model/<id>` ARN (region wildcard, **model id still exact**). That is required because the profile may invoke the FM outside this stack’s region; it is not a blanket `bedrock:*` grant.
3. `terraform apply`

Lambda always uses `CREW_MODE=agentcore`. Apply fails if the AgentCore runtime ARN is empty.

`AWS_ACCOUNT_ID` is not sensitive; using it from the shell just avoids committing account-specific values. `TF_VAR_serper_api_key` and `TF_VAR_google_places_api_key` are sensitive and should stay out of `terraform.tfvars`. When `GOOGLE_PLACES_API_KEY` is set on the API Lambda, plan-next-day / suggest-place enrich venues via Google Places API (New) before quality gates; omit the key to keep crew/Serper status only.

API Lambda always gets `PRODUCT_METRICS_HASH_PEPPER` (for non-reversible `user_sub` hashes in product metrics). Leave `product_metrics_hash_pepper` empty to let Terraform generate a stable random pepper in state, or set `TF_VAR_product_metrics_hash_pepper` to inject your own secret.

**Google Places key restrictions:** restrict the key to Places API (New) only, and prefer IP restriction to Lambda egress. `sensitive = true` redacts CLI output only — the value still sits in Terraform state and Lambda env (same as Serper). Move both to Secrets Manager/SSM when hardening beyond this MVP.

## Least privilege model

IAM policies are intentionally scoped to the resources created or configured by this stack:

| Principal | Allowed access |
| --- | --- |
| Backend Lambda role | `GetItem`, `PutItem`, `UpdateItem`, and `Query` on this stack's DynamoDB table and its indexes; log-stream writes only to its own `/aws/lambda/${project}-${env}-api` log group; invoke on the configured AgentCore runtime ARN; `bedrock:ApplyGuardrail` only when `safety_mode` is `bedrock`/`guardrails` and a Guardrail ARN is set. |
| AgentCore runtime role | Pulls only the configured ECR repository image; gets an ECR auth token (AWS requires `Resource = "*"`); writes only to AgentCore runtime log groups under `/aws/bedrock-agentcore/runtimes/*`; when GenAI observability is enabled: X-Ray put/sampling + `cloudwatch:PutMetricData` in namespace `bedrock-agentcore`; invokes only models from `agent_bedrock_models` (or `agent_allowed_bedrock_model_arns` override). |
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
| Account/region (`observability/`) | CloudWatch Logs resource policy (`VacationPlannerTransactionSearchXRay`) for X-Ray → `aws/spans`, `/aws/application-signals/data`, `/aws/bedrock-agentcore/runtimes/*`; `awscc_xray_transaction_search_config` (indexing %, default **1** = free tier). The Logs resource policy is the one-time X-Ray write grant — the runtime role does **not** get `logs:PutResourcePolicy`. |
| AgentCore runtime | Only when observability is enabled: ADOT env (`AGENT_OBSERVABILITY_ENABLED=true`, distro/configurator, `UNIFIED_TRACES_DESTINATION_ENABLED`, `service.name`, `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=NO_CONTENT`); IAM: X-Ray put/sampling, `cloudwatch:PutMetricData` (`bedrock-agentcore`) |
| Agent image | Neutral by default (`entrypoint.sh`). ADOT (`opentelemetry-instrument`) runs only when AgentCore sets `AGENT_OBSERVABILITY_ENABLED=true`. |

**Account singleton:** Transaction Search is one config per account+region. Keep `enable_genai_observability = true` in **only one** stack (e.g. `dev`). Other envs should set it `false` (or share this stack’s state).

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
- Google IdP is skipped when `google_client_id` / `google_client_secret` are empty.
- Facebook IdP is skipped when `facebook_app_id` / `facebook_app_secret` are empty.
- After apply, `terraform output cognito_identity_providers` lists enabled IdPs for `VITE_COGNITO_IDENTITY_PROVIDERS` (set automatically by `frontend/scripts/deploy.sh`).
- **Facebook `attributes required: [email]`:** Cognito requires email. In Meta Developer Console → App → **App Review → Permissions and features**, grant **Advanced Access** for `email` (and `public_profile`). Use a Facebook account that has a primary email and accept the email permission on the consent screen. Then `terraform apply` so Cognito IdP scopes are `public_profile, email`.
- Do not commit `terraform.tfvars`, `.terraform/`, or `*.tfstate*`.
