output "enabled" {
  value = var.enabled
}

output "trace_segment_destination" {
  description = "Expected X-Ray destination after TransactionSearchConfig is active"
  value       = var.enabled ? "CloudWatchLogs" : null
}

output "indexing_percentage" {
  value = var.enabled ? var.indexing_percentage : null
}

output "log_resource_policy_name" {
  value = try(aws_cloudwatch_log_resource_policy.transaction_search[0].policy_name, null)
}

output "account_id" {
  value = try(awscc_xray_transaction_search_config.this[0].account_id, null)
}
