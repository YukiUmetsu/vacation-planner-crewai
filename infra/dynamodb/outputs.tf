output "table_name" {
  value = aws_dynamodb_table.this.name
}

output "table_arn" {
  value = aws_dynamodb_table.this.arn
}

output "metrics_table_name" {
  value = aws_dynamodb_table.metrics.name
}

output "metrics_table_arn" {
  value = aws_dynamodb_table.metrics.arn
}
