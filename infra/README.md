# Infrastructure (Terraform)

Provisions the AWS stack for Vacation Planner:

| Module | Resources |
| --- | --- |
| `dynamodb/` | Single-table `${project}-${env}-table` (`pk`/`sk`, GSI1, TTL on `expires_at`) |
| `cognito/` | User pool, app client, Hosted UI domain; optional Google IdP |
| `api/` | Lambda (from `backend/src`) + HTTP API + Cognito JWT authorizer |
| `frontend/` | S3 + CloudFront (OAC) for the SPA |
| `agentcore/` | Bedrock AgentCore runtime (optional; needs ECR image) |

Schema details: [`docs/DATA_MODEL.md`](../docs/DATA_MODEL.md).

## Prerequisites

- Terraform `>= 1.5`
- AWS credentials with permission to create the resources above
- AWS provider `>= 6.17` (AgentCore resources)
- Optional: Google OAuth client for Hosted UI social login
- Optional: ECR image of the agent for AgentCore

## Quick start

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars (and/or export TF_VAR_google_client_secret, TF_VAR_serper_api_key)

terraform init
terraform plan
terraform apply
```

Useful outputs after apply:

- `api_endpoint` → frontend `VITE_API_URL`
- `cognito_user_pool_id` / `cognito_user_pool_client_id` / `cognito_hosted_ui_domain`
- `frontend_site_url` / `frontend_bucket_name` → upload `frontend` build
- `agent_runtime_arn` → set when AgentCore is enabled

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

### Enable AgentCore

1. Build and push an agent container to ECR.
2. Set in `terraform.tfvars`:

```hcl
enable_agentcore            = true
agent_runtime_container_uri = "ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/vacation-planner-agent:latest"
```

3. Prefer `export TF_VAR_serper_api_key=...` over committing the key.
4. `terraform apply`

## Layout

```text
infra/
  main.tf / variables.tf / outputs.tf / versions.tf / providers.tf
  terraform.tfvars.example
  dynamodb/
  cognito/
  api/           # zips ../backend/src → Lambda
  frontend/
  agentcore/
```

## Notes

- Backend Lambda currently ships the stub in `backend/src` (returns 501). Re-apply after implementing routes.
- Google IdP is skipped when `google_client_id` / `google_client_secret` are empty.
- Do not commit `terraform.tfvars`, `.terraform/`, or `*.tfstate*`.
