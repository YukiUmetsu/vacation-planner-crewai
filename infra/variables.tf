variable "project_name" {
  description = "Short name used in resource names and tags"
  type        = string
  default     = "vacation-planner"
}

variable "environment" {
  description = "Deployment environment label (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "google_client_id" {
  description = "Google OAuth client ID for Cognito Hosted UI (leave empty to skip Google IdP)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "google_client_secret" {
  description = "Google OAuth client secret for Cognito Hosted UI"
  type        = string
  default     = ""
  sensitive   = true
}

variable "facebook_app_id" {
  description = "Facebook Login App ID for Cognito Hosted UI (leave empty to skip Facebook IdP)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "facebook_app_secret" {
  description = "Facebook Login App Secret for Cognito Hosted UI"
  type        = string
  default     = ""
  sensitive   = true
}

variable "callback_urls" {
  description = "Allowed Cognito Hosted UI callback URLs (frontend)"
  type        = list(string)
  default     = ["http://localhost:5173/callback"]
}

variable "logout_urls" {
  description = "Allowed Cognito Hosted UI logout URLs"
  type        = list(string)
  default     = ["http://localhost:5173/"]
}

variable "enable_agentcore" {
  description = "Create Bedrock AgentCore runtime (required for API deploy; needs ECR image URI + Bedrock model ARNs)"
  type        = bool
  default     = true
}

variable "enable_genai_observability" {
  description = "Enable CloudWatch Transaction Search + AgentCore ADOT wiring. Account/region singleton — enable in only one stack per region."
  type        = bool
  default     = true
}

variable "genai_observability_indexing_percentage" {
  description = "Percent of spans indexed for Transaction Search (1 is free; raise for denser GenAI dashboards)"
  type        = number
  default     = 1

  validation {
    condition     = var.genai_observability_indexing_percentage >= 0 && var.genai_observability_indexing_percentage <= 100
    error_message = "genai_observability_indexing_percentage must be between 0 and 100."
  }
}

variable "agent_runtime_container_uri" {
  description = "ECR image URI for AgentCore runtime (e.g. 123.dkr.ecr.us-east-1.amazonaws.com/vacation-agent:latest)"
  type        = string
  default     = ""
}

variable "agent_bedrock_models" {
  description = <<-EOT
    Bedrock model IDs AgentCore may invoke (same as crew llm after "bedrock/").
    Example: ["us.amazon.nova-pro-v1:0"]. Terraform expands these to IAM ARNs.
  EOT
  type        = list(string)
  default     = ["us.amazon.nova-pro-v1:0"]
}

variable "agent_allowed_bedrock_model_arns" {
  description = "Optional full Bedrock ARNs; when set, overrides agent_bedrock_models expansion"
  type        = list(string)
  default     = []
}

variable "serper_api_key" {
  description = "Optional Serper key stored in Secrets Manager and passed to AgentCore env"
  type        = string
  default     = ""
  sensitive   = true
}

variable "google_places_api_key" {
  description = "Optional Google Places API (New) key for BFF open-status enrichment on plan-next-day / suggest-place"
  type        = string
  default     = ""
  sensitive   = true
}

variable "product_metrics_hash_pepper" {
  description = "Optional override for API Lambda PRODUCT_METRICS_HASH_PEPPER (user_sub hashing). Empty → Terraform generates a stable random pepper."
  type        = string
  default     = ""
  sensitive   = true
}

variable "metrics_admin_subs" {
  description = "Comma-separated Cognito user subs allowed to use GET /admin/metrics (empty disables admin metrics)."
  type        = string
  default     = ""
}

variable "safety_mode" {
  description = "API Lambda SAFETY_MODE: keyword (default), bedrock/guardrails (ApplyGuardrail), or off."
  type        = string
  default     = "keyword"

  validation {
    condition     = contains(["keyword", "bedrock", "guardrails", "off", "noop", "none"], var.safety_mode)
    error_message = "safety_mode must be keyword, bedrock, guardrails, or off."
  }
}

variable "enable_bedrock_guardrails" {
  description = "Create the Bedrock Guardrail module (content/PII/topics/words). Safe to enable before SAFETY_MODE=bedrock."
  type        = bool
  default     = true
}

variable "bedrock_guardrail_id" {
  description = "Override Guardrail ID when enable_bedrock_guardrails=false (external Guardrail)"
  type        = string
  default     = ""
}

variable "bedrock_guardrail_version" {
  description = "Override Guardrail version when enable_bedrock_guardrails=false"
  type        = string
  default     = "DRAFT"
}

variable "bedrock_guardrail_arn" {
  description = "Override Guardrail ARN when enable_bedrock_guardrails=false (required for ApplyGuardrail IAM)"
  type        = string
  default     = ""
}
