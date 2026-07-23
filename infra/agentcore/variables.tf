variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "enabled" {
  type    = bool
  default = false
}

variable "container_uri" {
  description = "ECR image URI for the AgentCore runtime container"
  type        = string
  default     = ""
}

variable "bedrock_models" {
  description = <<-EOT
    Bedrock model IDs the runtime may invoke — same suffix as crew llm after "bedrock/"
    (e.g. us.amazon.nova-pro-v1:0). Terraform expands these to inference-profile +
    foundation-model ARNs. Prefer this over bedrock_model_arns.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for id in var.bedrock_models :
      length(trimspace(id)) > 0 && !can(regex("^arn:", id)) && !can(regex("(REGION|ACCOUNT|YOUR_PROFILE|REPLACE)", id))
    ])
    error_message = "bedrock_models entries must be model IDs like us.amazon.nova-pro-v1:0, not ARNs."
  }
}

variable "bedrock_model_arns" {
  description = "Optional full Bedrock ARNs. When non-empty, overrides expansion from bedrock_models."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for arn in var.bedrock_model_arns :
      can(regex("^arn:aws:bedrock:([a-z0-9-]+|\\*):([0-9]{12})?:(foundation-model|inference-profile|provisioned-model)/.+", arn))
      && !can(regex("(REGION|ACCOUNT|YOUR_PROFILE|REPLACE)", arn))
    ])
    error_message = "Each entry must be a real Bedrock ARN (not a placeholder). Prefer bedrock_models IDs instead."
  }
}

variable "serper_api_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "observability_enabled" {
  description = "Wire ADOT/GenAI Observability env + IAM on the AgentCore runtime (pair with account Transaction Search)"
  type        = bool
  default     = true
}
