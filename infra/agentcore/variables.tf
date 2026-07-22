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

variable "bedrock_model_arns" {
  description = "Exact Bedrock foundation model, inference profile, or provisioned model ARNs the agent runtime may invoke"
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for arn in var.bedrock_model_arns : can(regex("^arn:", arn))])
    error_message = "Each Bedrock model entry must be an ARN."
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
