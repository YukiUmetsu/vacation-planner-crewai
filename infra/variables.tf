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
  description = "Create Bedrock AgentCore runtime"
  type        = bool
  default     = true
}

variable "agent_runtime_container_uri" {
  description = "ECR image URI for AgentCore runtime (e.g. 123.dkr.ecr.us-east-1.amazonaws.com/vacation-agent:latest)"
  type        = string
  default     = ""
}

variable "agent_allowed_bedrock_model_arns" {
  description = "Exact Bedrock model or inference profile ARNs the AgentCore runtime may invoke"
  type        = list(string)
  default     = []
}

variable "serper_api_key" {
  description = "Optional Serper key stored in Secrets Manager and passed to AgentCore env"
  type        = string
  default     = ""
  sensitive   = true
}
