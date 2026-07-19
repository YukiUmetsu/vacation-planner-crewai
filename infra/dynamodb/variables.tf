variable "table_name" {
  description = "DynamoDB table name"
  type        = string
}

variable "enable_ttl" {
  description = "Enable TTL on expires_at attribute"
  type        = bool
  default     = true
}
