locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

module "dynamodb" {
  source     = "./dynamodb"
  table_name = "${local.name_prefix}-table"
}

module "cognito" {
  source               = "./cognito"
  project_name         = var.project_name
  environment          = var.environment
  google_client_id     = var.google_client_id
  google_client_secret = var.google_client_secret
  callback_urls        = var.callback_urls
  logout_urls          = var.logout_urls
}

module "agentcore" {
  source                = "./agentcore"
  project_name          = var.project_name
  environment           = var.environment
  enabled               = var.enable_agentcore
  container_uri         = var.agent_runtime_container_uri
  bedrock_model_arns    = var.agent_allowed_bedrock_model_arns
  serper_api_key        = var.serper_api_key
  observability_enabled = var.enable_genai_observability
}

# Account/region Transaction Search — required for CloudWatch GenAI Observability.
module "observability" {
  source              = "./observability"
  project_name        = var.project_name
  environment         = var.environment
  enabled             = var.enable_genai_observability
  indexing_percentage = var.genai_observability_indexing_percentage
}

module "guardrails" {
  source       = "./guardrails"
  project_name = var.project_name
  environment  = var.environment
  enabled      = var.enable_bedrock_guardrails
  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

locals {
  # Prefer Terraform-managed Guardrail; allow external overrides when the module is off.
  bedrock_guardrail_id = (
    var.enable_bedrock_guardrails
    ? module.guardrails.guardrail_id
    : var.bedrock_guardrail_id
  )
  bedrock_guardrail_version = (
    var.enable_bedrock_guardrails
    ? module.guardrails.version
    : var.bedrock_guardrail_version
  )
  bedrock_guardrail_arn = (
    var.enable_bedrock_guardrails
    ? module.guardrails.guardrail_arn
    : var.bedrock_guardrail_arn
  )
}

module "api" {
  source = "./api"

  project_name                = var.project_name
  environment                 = var.environment
  dynamodb_table_name         = module.dynamodb.table_name
  dynamodb_table_arn          = module.dynamodb.table_arn
  cognito_user_pool_client_id = module.cognito.user_pool_client_id
  cognito_issuer              = module.cognito.issuer
  agent_runtime_arn           = module.agentcore.agent_runtime_arn
  safety_mode                 = var.safety_mode
  bedrock_guardrail_id        = local.bedrock_guardrail_id
  bedrock_guardrail_version   = local.bedrock_guardrail_version
  bedrock_guardrail_arn       = local.bedrock_guardrail_arn
  google_places_api_key       = var.google_places_api_key
  # Built package (src + pip deps). Run: ../backend/scripts/build_lambda.sh
  backend_source_dir = "${path.root}/../backend/.build/lambda"
}

module "frontend" {
  source       = "./frontend"
  project_name = var.project_name
  environment  = var.environment
}
