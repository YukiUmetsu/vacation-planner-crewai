output "user_pool_id" {
  value = aws_cognito_user_pool.this.id
}

output "user_pool_arn" {
  value = aws_cognito_user_pool.this.arn
}

output "user_pool_client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "user_pool_endpoint" {
  value = aws_cognito_user_pool.this.endpoint
}

output "hosted_ui_domain" {
  value = "${aws_cognito_user_pool_domain.this.domain}.auth.${data.aws_region.current.region}.amazoncognito.com"
}

output "issuer" {
  value = "https://cognito-idp.${data.aws_region.current.region}.amazonaws.com/${aws_cognito_user_pool.this.id}"
}

output "identity_providers" {
  description = "Cognito app-client supported IdPs (COGNITO plus optional Google/Facebook)"
  # Provider names are not secrets; enable flags are derived from sensitive vars.
  value = nonsensitive(local.identity_providers)
}

data "aws_region" "current" {}
