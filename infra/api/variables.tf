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
  description = "Optional AgentCore runtime ARN for invoke permission"
  type        = string
  default     = ""
}

variable "backend_source_dir" {
  description = "Path to built Lambda package dir (run backend/scripts/build_lambda.sh → backend/.build/lambda)"
  type        = string
}
