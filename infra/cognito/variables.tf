variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "google_client_id" {
  type      = string
  sensitive = true
}

variable "google_client_secret" {
  type      = string
  sensitive = true
}

variable "facebook_app_id" {
  type        = string
  sensitive   = true
  description = "Facebook Login App ID (empty skips Facebook IdP)"
  default     = ""
}

variable "facebook_app_secret" {
  type        = string
  sensitive   = true
  description = "Facebook Login App Secret (empty skips Facebook IdP)"
  default     = ""
}

variable "callback_urls" {
  type = list(string)
}

variable "logout_urls" {
  type = list(string)
}
