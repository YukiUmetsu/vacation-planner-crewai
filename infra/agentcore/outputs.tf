output "agent_runtime_arn" {
  value = try(aws_bedrockagentcore_agent_runtime.this[0].agent_runtime_arn, "")
}

output "agent_runtime_id" {
  value = try(aws_bedrockagentcore_agent_runtime.this[0].agent_runtime_id, "")
}

output "runtime_role_arn" {
  value = try(aws_iam_role.runtime[0].arn, "")
}
