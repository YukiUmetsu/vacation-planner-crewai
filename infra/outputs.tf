output "dynamodb_table_name" {
  value = module.dynamodb.table_name
}

output "dynamodb_metrics_table_name" {
  value = module.dynamodb.metrics_table_name
}

output "cognito_user_pool_id" {
  value = module.cognito.user_pool_id
}

output "cognito_user_pool_client_id" {
  value = module.cognito.user_pool_client_id
}

output "cognito_hosted_ui_domain" {
  value = module.cognito.hosted_ui_domain
}

output "cognito_issuer" {
  value = module.cognito.issuer
}

output "cognito_identity_providers" {
  description = "Enabled Cognito identity providers for the SPA (comma-join into VITE_COGNITO_IDENTITY_PROVIDERS)"
  value       = module.cognito.identity_providers
}

output "cognito_google_secret_name" {
  value = module.secrets.cognito_google_secret_name
}

output "cognito_facebook_secret_name" {
  value = module.secrets.cognito_facebook_secret_name
}

output "serper_secret_arn" {
  value = module.secrets.serper_secret_arn
}

output "google_places_secret_arn" {
  value = module.secrets.google_places_secret_arn
}

output "product_metrics_pepper_secret_arn" {
  value = module.secrets.product_metrics_pepper_secret_arn
}

output "api_endpoint" {
  description = "HTTP API base URL for the frontend"
  value       = module.api.api_endpoint
}

output "api_logs_dashboard_name" {
  description = "CloudWatch ops dashboard (API log ERROR/WARNING + Lambda/AgentCore built-in metrics)"
  value       = module.api.api_logs_dashboard_name
}

output "lambda_log_group_name" {
  value = module.api.lambda_log_group_name
}

output "frontend_bucket_name" {
  value = module.frontend.bucket_name
}

output "frontend_site_url" {
  value = module.frontend.site_url
}

output "cloudfront_distribution_id" {
  value = module.frontend.cloudfront_distribution_id
}

output "agent_runtime_arn" {
  value = module.agentcore.agent_runtime_arn
}

output "genai_observability_enabled" {
  description = "Whether Terraform configured CloudWatch Transaction Search for GenAI Observability"
  value       = module.observability.enabled
}

output "genai_observability_trace_destination" {
  description = "X-Ray trace segment destination when GenAI observability is enabled"
  value       = module.observability.trace_segment_destination
}

output "bedrock_guardrail_id" {
  value = local.bedrock_guardrail_id
}

output "bedrock_guardrail_version" {
  value = local.bedrock_guardrail_version
}

output "bedrock_guardrail_arn" {
  value = local.bedrock_guardrail_arn
}
