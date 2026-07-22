variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "dynamodb_table_name" {
  type = string
}

variable "dynamodb_table_arn" {
  type = string
}

variable "cognito_user_pool_client_id" {
  type = string
}

variable "cognito_issuer" {
  type = string
}

variable "agent_runtime_arn" {
  description = "AgentCore runtime ARN (required for API Lambda CREW_MODE=agentcore)"
  type        = string
}

variable "safety_mode" {
  description = "Lambda SAFETY_MODE: keyword (default) or off until ApplyGuardrail is implemented"
  type        = string
  default     = "keyword"
}

variable "bedrock_guardrail_id" {
  description = "Bedrock Guardrail ID when SAFETY_MODE=bedrock (empty until Guardrails are implemented)"
  type        = string
  default     = ""
}

variable "bedrock_guardrail_version" {
  description = "Bedrock Guardrail version (e.g. DRAFT or 1)"
  type        = string
  default     = "DRAFT"
}

variable "bedrock_guardrail_arn" {
  description = "Bedrock Guardrail ARN for ApplyGuardrail IAM (empty skips the statement)"
  type        = string
  default     = ""
}

variable "backend_source_dir" {
  description = "Path to built Lambda package dir (run backend/scripts/build_lambda.sh → backend/.build/lambda)"
  type        = string
}
