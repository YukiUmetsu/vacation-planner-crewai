output "guardrail_id" {
  description = "Bedrock Guardrail ID (empty when module disabled)"
  value       = try(aws_bedrock_guardrail.trips[0].guardrail_id, "")
}

output "guardrail_arn" {
  description = "Bedrock Guardrail ARN (empty when module disabled)"
  value       = try(aws_bedrock_guardrail.trips[0].guardrail_arn, "")
}

output "version" {
  description = "Published version string, or DRAFT when publish_version=false / disabled"
  value = (
    var.enabled && var.publish_version
    ? aws_bedrock_guardrail_version.trips[0].version
    : try(aws_bedrock_guardrail.trips[0].version, "DRAFT")
  )
}
