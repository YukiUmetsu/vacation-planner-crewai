locals {
  name_prefix     = "${var.project_name}-${var.environment}"
  enable_google   = var.enable_google_idp
  enable_facebook = var.enable_facebook_idp
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

# Social IdP credentials live in Secrets Manager and are applied by
# infra/scripts/sync_cognito_idps_from_secrets.sh (Cognito has no client_secret_wo yet).
# These removed blocks drop IdP resources from Terraform state without destroying AWS IdPs.
removed {
  from = aws_cognito_identity_provider.google

  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_cognito_identity_provider.facebook

  lifecycle {
    destroy = false
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
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = "${local.name_prefix}-${substr(md5(var.project_name), 0, 8)}"
  user_pool_id = aws_cognito_user_pool.this.id
}
