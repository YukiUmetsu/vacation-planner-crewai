variable "enabled" {
  description = "Enable CloudWatch Transaction Search + GenAI Observability account wiring for this region"
  type        = bool
  default     = true
}

variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "indexing_percentage" {
  description = "Percent of ingested spans indexed for Transaction Search (1 is free tier)"
  type        = number
  default     = 1

  validation {
    condition     = var.indexing_percentage >= 0 && var.indexing_percentage <= 100
    error_message = "indexing_percentage must be between 0 and 100."
  }
}
