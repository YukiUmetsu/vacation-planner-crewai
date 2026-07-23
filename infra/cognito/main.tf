locals {
  enable_google   = var.google_client_id != "" && var.google_client_secret != ""
  enable_facebook = var.facebook_app_id != "" && var.facebook_app_secret != ""
  name_prefix     = "${var.project_name}-${var.environment}"
  identity_providers = concat(
    ["COGNITO"],
    local.enable_google ? ["Google"] : [],
    local.enable_facebook ? ["Facebook"] : [],
  )
}

resource "aws_cognito_user_pool" "this" {
  name = "${local.name_prefix}-users"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}

resource "aws_cognito_identity_provider" "google" {
  count = local.enable_google ? 1 : 0

  user_pool_id  = aws_cognito_user_pool.this.id
  provider_name = "Google"
  provider_type = "Google"

  provider_details = {
    client_id                     = var.google_client_id
    client_secret                 = var.google_client_secret
    authorize_scopes              = "openid email profile"
    attributes_url_add_attributes = "true"
  }

  attribute_mapping = {
    email    = "email"
    username = "sub"
  }

  # AWS injects authorize_url / token_url / oidc_issuer / etc. after create.
  # Ignoring them avoids perpetual plan noise (-> null).
  lifecycle {
    ignore_changes = [
      provider_details["attributes_url"],
      provider_details["attributes_url_add_attributes"],
      provider_details["authorize_url"],
      provider_details["oidc_issuer"],
      provider_details["token_request_method"],
      provider_details["token_url"],
    ]
  }
}

resource "aws_cognito_identity_provider" "facebook" {
  count = local.enable_facebook ? 1 : 0

  user_pool_id  = aws_cognito_user_pool.this.id
  provider_name = "Facebook"
  provider_type = "Facebook"

  # Scopes must match AWS Facebook format (comma+space). email is required by our user pool.
  provider_details = {
    api_version      = "v21.0"
    authorize_scopes = "public_profile, email"
    client_id        = var.facebook_app_id
    client_secret    = var.facebook_app_secret
  }

  attribute_mapping = {
    email              = "email"
    name               = "name"
    preferred_username = "id"
    username           = "id"
  }

  lifecycle {
    ignore_changes = [
      provider_details["attributes_url"],
      provider_details["attributes_url_add_attributes"],
      provider_details["authorize_url"],
      provider_details["token_request_method"],
      provider_details["token_url"],
    ]
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "${local.name_prefix}-web"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret                      = false
  prevent_user_existence_errors        = "ENABLED"
  supported_identity_providers         = local.identity_providers
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  callback_urls                        = var.callback_urls
  logout_urls                          = var.logout_urls
  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  depends_on = [
    aws_cognito_identity_provider.google,
    aws_cognito_identity_provider.facebook,
  ]
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = "${local.name_prefix}-${substr(md5(var.project_name), 0, 8)}"
  user_pool_id = aws_cognito_user_pool.this.id
}
