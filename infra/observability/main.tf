# Account/region GenAI Observability prerequisites for AgentCore.
# Official path: Logs resource policy + AWS::XRay::TransactionSearchConfig
# https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Transaction-Search-Cloudformation.html
#
# These settings are account+region singletons. Enable in only one stack per
# region (see enable_genai_observability). If Transaction Search is already on,
# import before apply (see module README / infra README).

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

locals {
  create = var.enabled

  # Stable account-scoped name (not env-prefixed) so re-applies/re-envs do not
  # proliferate CloudWatch Logs account resource policies (limit ~10).
  policy_name = "VacationPlannerTransactionSearchXRay"

  spans_log_group_arn               = "arn:${data.aws_partition.current.partition}:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:aws/spans:*"
  application_signals_log_group_arn = "arn:${data.aws_partition.current.partition}:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/application-signals/data:*"
  agentcore_runtime_log_group_arn   = "arn:${data.aws_partition.current.partition}:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:*"
  xray_source_arn                   = "arn:${data.aws_partition.current.partition}:xray:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:*"
}

data "aws_iam_policy_document" "transaction_search_xray" {
  count = local.create ? 1 : 0

  statement {
    sid    = "TransactionSearchXRayAccess"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["xray.amazonaws.com"]
    }

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = [
      local.spans_log_group_arn,
      local.application_signals_log_group_arn,
      local.agentcore_runtime_log_group_arn,
    ]

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = [local.xray_source_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_cloudwatch_log_resource_policy" "transaction_search" {
  count = local.create ? 1 : 0

  policy_name     = local.policy_name
  policy_document = data.aws_iam_policy_document.transaction_search_xray[0].json
}

# Enables Transaction Search (X-Ray → CloudWatch Logs) and span indexing.
# Prefer this over managing Default indexing rule / destination separately —
# those are easy to conflict with existing account state.
resource "awscc_xray_transaction_search_config" "this" {
  count = local.create ? 1 : 0

  indexing_percentage = var.indexing_percentage

  depends_on = [aws_cloudwatch_log_resource_policy.transaction_search]
}
