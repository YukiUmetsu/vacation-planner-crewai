variable "table_name" {
  description = "DynamoDB table name (trips / routes / days / profile)"
  type        = string
}

variable "metrics_table_name" {
  description = "DynamoDB table name for offline eval / admin metrics"
  type        = string
}

variable "enable_ttl" {
  description = "Enable TTL on expires_at attribute (trip table only)"
  type        = bool
  default     = true
}
