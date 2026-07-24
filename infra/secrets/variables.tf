variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "bootstrap_product_metrics_pepper" {
  description = "When true, write an ephemeral random pepper into SM via secret_string_wo (value not stored in Terraform state)."
  type        = bool
  default     = true
}
