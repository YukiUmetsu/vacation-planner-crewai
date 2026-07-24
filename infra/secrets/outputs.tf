output "cognito_google_secret_arn" {
  value = aws_secretsmanager_secret.cognito_google.arn
}

output "cognito_google_secret_name" {
  value = aws_secretsmanager_secret.cognito_google.name
}

output "cognito_facebook_secret_arn" {
  value = aws_secretsmanager_secret.cognito_facebook.arn
}

output "cognito_facebook_secret_name" {
  value = aws_secretsmanager_secret.cognito_facebook.name
}

output "serper_secret_arn" {
  value = aws_secretsmanager_secret.serper.arn
}

output "serper_secret_name" {
  value = aws_secretsmanager_secret.serper.name
}

output "google_places_secret_arn" {
  value = aws_secretsmanager_secret.google_places.arn
}

output "google_places_secret_name" {
  value = aws_secretsmanager_secret.google_places.name
}

output "product_metrics_pepper_secret_arn" {
  value = aws_secretsmanager_secret.product_metrics_pepper.arn
}

output "product_metrics_pepper_secret_name" {
  value = aws_secretsmanager_secret.product_metrics_pepper.name
}
