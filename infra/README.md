# Infrastructure (Terraform)

Provisions the AWS stack for Vacation Planner:

| Module | Resources |
| --- | --- |
| `dynamodb/` | Single-table `${project}-${env}-table` (`pk`/`sk`, GSI1, TTL on `expires_at`) |
| `cognito/` | User pool, app client, Hosted UI domain; optional Google IdP |
| `api/` | Lambda (from `backend/.build/lambda` — run `backend/scripts/build_lambda.sh` first) + HTTP API + Cognito JWT authorizer |
| `frontend/` | S3 + CloudFront (OAC) for the SPA |
| `agentcore/` | Bedrock AgentCore runtime (optional; needs ECR image) |

Schema details: [`docs/DATA_MODEL.md`](../docs/DATA_MODEL.md).

## Prerequisites

- Terraform `>= 1.5`
- AWS credentials with permission to create the resources above
- AWS provider `>= 6.17` (AgentCore resources)
- Optional: Google OAuth client for Hosted UI social login
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

```bash
cd ../frontend
npm install && npm run build
aws s3 sync dist/ "s3://$(cd ../infra && terraform output -raw frontend_bucket_name)/" --delete
aws cloudfront create-invalidation \
  --distribution-id "$(cd ../infra && terraform output -raw cloudfront_distribution_id)" \
  --paths "/*"
```

Then add the CloudFront URL to `callback_urls` / `logout_urls` and `terraform apply` again.

### Configure AgentCore

1. Build and push an agent container to ECR (and implement `agent/main.py` + backend `CREW_MODE=agentcore` — Day 2).
2. Set `enable_agentcore = true` in `terraform.tfvars`, plus the runtime image and exact Bedrock model ARNs. Prefer env vars for account-specific / secret values:

```bash
export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export TF_VAR_agent_runtime_container_uri="${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/vacation-planner-agent:latest"
export TF_VAR_agent_allowed_bedrock_model_arns='["REPLACE_WITH_EXACT_BEDROCK_MODEL_OR_INFERENCE_PROFILE_ARN"]'
export TF_VAR_serper_api_key="REPLACE_WITH_SERPER_API_KEY"
```

3. `terraform apply`

Lambda ships with `CREW_MODE=agentcore` (production). Planning calls need a live runtime ARN plus the Day 2 AgentCore CrewRunner.

`AWS_ACCOUNT_ID` is not sensitive; using it from the shell just avoids committing account-specific values. `TF_VAR_serper_api_key` is sensitive and should stay out of `terraform.tfvars`.

## Least privilege model

IAM policies are intentionally scoped to the resources created or configured by this stack:

| Principal | Allowed access |
| --- | --- |
| Backend Lambda role | `GetItem`, `PutItem`, `UpdateItem`, and `Query` on this stack's DynamoDB table and its indexes; log-stream writes only to its own `/aws/lambda/${project}-${env}-api` log group; optional invoke on the configured AgentCore runtime ARN only. |
| AgentCore runtime role | Pulls only the configured ECR repository image; gets an ECR auth token (AWS requires `Resource = "*"`); writes only to AgentCore runtime log groups under `/aws/bedrock-agentcore/runtimes/*`; invokes only ARNs listed in `agent_allowed_bedrock_model_arns`. |
| CloudFront service principal | Reads objects from only the generated frontend bucket, constrained by the distribution `AWS:SourceArn`. |

AgentCore is **off by default** (`enable_agentcore = false`). When you enable it, `agent_runtime_container_uri` must be a standard ECR image URI and `agent_allowed_bedrock_model_arns` must be non-empty; this avoids granting `bedrock:*` or wildcard model invocation just to make a demo work. If the crew switches models, update that list deliberately. The Bedrock ARN format depends on whether you use a foundation model, inference profile, or provisioned model, so copy the exact ARN for the resource your crew calls.

The AgentCore log permissions use the AWS-documented runtime log group prefix `/aws/bedrock-agentcore/runtimes/*` because the concrete runtime/endpoint log group name is assigned by AgentCore after creation.

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
```

## Notes

- Trip API routes are implemented in `backend/src`. Redeploy after `./scripts/build_lambda.sh` so the zip picks up code changes.
- Lambda `CREW_MODE` is **`agentcore`** (production). Enable AgentCore (`enable_agentcore=true` + ECR image + model ARNs) before relying on propose/plan routes in AWS; local work uses `CREW_MODE=fake`.
- `enable_agentcore` defaults to **false**. Set it true only with a real ECR URI and non-empty `agent_allowed_bedrock_model_arns`, or apply fails on AgentCore preconditions.
- Google IdP is skipped when `google_client_id` / `google_client_secret` are empty.
- Do not commit `terraform.tfvars`, `.terraform/`, or `*.tfstate*`.
