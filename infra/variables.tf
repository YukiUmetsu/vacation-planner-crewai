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

variable "enable_google_idp" {
  description = "List Google on the Cognito app client. Seed credentials into SM and run sync_cognito_idps_from_secrets.sh."
  type        = bool
  default     = true
}

variable "enable_facebook_idp" {
  description = "List Facebook on the Cognito app client. Seed credentials into SM and run sync_cognito_idps_from_secrets.sh."
  type        = bool
  default     = true
}

variable "callback_urls" {
  description = "Extra Cognito Hosted UI callback URLs (localhost defaults). This stack's CloudFront URL is always merged in automatically."
  type        = list(string)
  default     = ["http://localhost:5173/callback"]
}

variable "logout_urls" {
  description = "Extra Cognito Hosted UI logout URLs (localhost defaults). This stack's CloudFront URL is always merged in automatically."
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
  description = <<-EOT
    Percent of spans indexed for Transaction Search / GenAI Observability.
    1 is free-tier; at low invoke volume the Agents View often shows 0 indexed
    traces — raise (e.g. 100) while debugging, then lower again if desired.
  EOT
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

variable "metrics_admin_subs" {
  description = "Comma-separated Cognito user subs allowed as admin break-glass (empty disables unless ADMIN_EMAILS / PROFILE role)."
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

variable "safety_mode" {
  description = "API Lambda SAFETY_MODE: bedrock/guardrails (ApplyGuardrail, recommended), keyword, or off."
  type        = string
  default     = "bedrock"

  validation {
    condition     = contains(["keyword", "bedrock", "guardrails", "off", "noop", "none"], var.safety_mode)
    error_message = "safety_mode must be keyword, bedrock, guardrails, or off."
  }
}

variable "safety_output_mode" {
  description = "SAFETY_OUTPUT_MODE: observe (log OUTPUT interventions, still persist) or enforce (reject). Aliases block/reject map to enforce at runtime."
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
