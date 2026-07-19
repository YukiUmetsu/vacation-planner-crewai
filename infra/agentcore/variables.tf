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

variable "serper_api_key" {
  type      = string
  default   = ""
  sensitive = true
}
