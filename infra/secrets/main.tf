locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

resource "aws_secretsmanager_secret" "cognito_google" {
  name                    = "${local.name_prefix}/cognito/google"
  description             = "Cognito Google IdP credentials JSON {client_id, client_secret}. Value set via CLI put-secret-value; not managed by Terraform."
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret" "cognito_facebook" {
  name                    = "${local.name_prefix}/cognito/facebook"
  description             = "Cognito Facebook IdP credentials JSON {app_id, app_secret}. Value set via CLI put-secret-value; not managed by Terraform."
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret" "serper" {
  name                    = "${local.name_prefix}/serper"
  description             = "Serper API key (plain string). Value set via CLI; AgentCore reads at runtime."
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret" "google_places" {
  name                    = "${local.name_prefix}/google-places"
  description             = "Google Places API key (plain string). Value set via CLI; API Lambda reads at runtime."
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret" "product_metrics_pepper" {
  name                    = "${local.name_prefix}/product-metrics-pepper"
  description             = "Pepper for PRODUCT_METRICS user_sub hashing. Bootstrap via ephemeral write-only version when enabled."
  recovery_window_in_days = 0
}

# Generate pepper in-memory and write to SM without storing the value in state.
ephemeral "random_password" "product_metrics_pepper" {
  length  = 48
  special = false
}

resource "aws_secretsmanager_secret_version" "product_metrics_pepper" {
  count = var.bootstrap_product_metrics_pepper ? 1 : 0

  secret_id                = aws_secretsmanager_secret.product_metrics_pepper.id
  secret_string_wo         = ephemeral.random_password.product_metrics_pepper.result
  secret_string_wo_version = 1
}
