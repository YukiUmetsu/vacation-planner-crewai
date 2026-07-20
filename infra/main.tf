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
  source             = "./agentcore"
  project_name       = var.project_name
  environment        = var.environment
  enabled            = var.enable_agentcore
  container_uri      = var.agent_runtime_container_uri
  bedrock_model_arns = var.agent_allowed_bedrock_model_arns
  serper_api_key     = var.serper_api_key
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
  # Built package (src + pip deps). Run: ../backend/scripts/build_lambda.sh
  backend_source_dir          = "${path.root}/../backend/.build/lambda"
}

module "frontend" {
  source       = "./frontend"
  project_name = var.project_name
  environment  = var.environment
}
