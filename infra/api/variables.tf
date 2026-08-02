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

variable "dynamodb_metrics_table_name" {
  description = "Dedicated DynamoDB table for offline eval / admin metrics"
  type        = string
}

variable "dynamodb_metrics_table_arn" {
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
  description = "Lambda SAFETY_MODE: bedrock/guardrails (recommended), keyword, or off"
  type        = string
  default     = "bedrock"
}

variable "safety_output_mode" {
  description = "Lambda SAFETY_OUTPUT_MODE: observe (default) or enforce. Aliases block/reject map to enforce."
  type        = string
  default     = "observe"

  validation {
    condition = contains(
      ["observe", "enforce", "block", "reject"],
      lower(var.safety_output_mode),
    )
    error_message = "safety_output_mode must be observe or enforce (aliases: block, reject)."
  }
}

variable "bedrock_guardrail_id" {
  description = "Bedrock Guardrail ID when SAFETY_MODE=bedrock"
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

variable "google_places_secret_arn" {
  description = "Secrets Manager ARN for Google Places API key (Lambda reads at runtime)"
  type        = string
  default     = ""
}

variable "amap_web_secret_arn" {
  description = "Secrets Manager ARN for Amap Web Service key (Lambda reads at runtime)"
  type        = string
  default     = ""
}

variable "product_metrics_pepper_secret_arn" {
  description = "Secrets Manager ARN for product metrics hash pepper (Lambda reads at runtime)"
  type        = string
  default     = ""
}

variable "secretsmanager_secret_arns" {
  description = "ARNs Lambda may GetSecretValue on"
  type        = list(string)
  default     = []
}

variable "metrics_admin_subs" {
  description = "Comma-separated Cognito subs for admin break-glass (empty → rely on ADMIN_EMAILS / PROFILE role)."
  type        = string
  default     = ""
}

variable "admin_emails" {
  description = "Comma-separated emails bootstrapped to PROFILE role=admin"
  type        = string
  default     = ""
}

variable "free_plan_max_trips" {
  description = "Max trips for non-admin free plan"
  type        = number
  default     = 1
}

variable "genai_cap_hour" {
  description = "Max GenAI actions per user per UTC hour"
  type        = number
  default     = 20
}

variable "genai_cap_day" {
  description = "Max GenAI actions per user per UTC day"
  type        = number
  default     = 100
}
