variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "enable_google_idp" {
  description = "List Google on the app client. Credentials are synced from Secrets Manager via sync_cognito_idps_from_secrets.sh."
  type        = bool
  default     = true
}

variable "enable_facebook_idp" {
  description = "List Facebook on the app client. Credentials are synced from Secrets Manager via sync_cognito_idps_from_secrets.sh."
  type        = bool
  default     = true
}

variable "callback_urls" {
  type = list(string)
}

variable "logout_urls" {
  type = list(string)
}
