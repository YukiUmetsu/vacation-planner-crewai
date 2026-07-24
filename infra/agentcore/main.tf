data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  name_prefix    = "${var.project_name}-${var.environment}"
  create_runtime = var.enabled
  # Agent runtime names: letters, numbers, underscore
  runtime_name = replace("${local.name_prefix}_agent", "-", "_")

  ecr_image_parts = local.create_runtime && can(regex("^([0-9]{12})\\.dkr\\.ecr\\.([a-z0-9-]+)\\.[^/]+/(.+)$", var.container_uri)) ? regex("^([0-9]{12})\\.dkr\\.ecr\\.([a-z0-9-]+)\\.[^/]+/(.+)$", var.container_uri) : []
  # Strip :tag or @digest without regexreplace (broader Terraform compatibility).
  ecr_image_ref       = length(local.ecr_image_parts) == 3 ? local.ecr_image_parts[2] : ""
  ecr_repository_name = local.ecr_image_ref != "" ? split(":", split("@", local.ecr_image_ref)[0])[0] : ""
  ecr_repository_arn  = local.ecr_repository_name != "" ? "arn:${data.aws_partition.current.partition}:ecr:${local.ecr_image_parts[1]}:${local.ecr_image_parts[0]}:repository/${local.ecr_repository_name}" : ""

  agentcore_log_group_arn  = "arn:${data.aws_partition.current.partition}:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
  agentcore_log_stream_arn = "${local.agentcore_log_group_arn}:log-stream:*"

  wire_observability = local.create_runtime && var.observability_enabled

  # Expand crew-style IDs (us.amazon.nova-pro-v1:0) into the ARNs IAM needs.
  #
  # Intentional least-privilege exception: the third ARN uses region=* on the
  # foundation-model resource. Cross-region inference profiles (us.* / eu.* / etc.)
  # invoke the underlying FM in a source region that may differ from this stack's
  # region; AWS requires that wildcard (or an explicit multi-region FM list).
  # Scope is still limited to the exact model id from var.bedrock_models — not bedrock:*.
  bedrock_arns_from_ids = distinct(flatten([
    for id in var.bedrock_models : [
      "arn:${data.aws_partition.current.partition}:bedrock:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:inference-profile/${id}",
      "arn:${data.aws_partition.current.partition}:bedrock:${data.aws_region.current.region}::foundation-model/${trimprefix(id, "us.")}",
      "arn:${data.aws_partition.current.partition}:bedrock:*::foundation-model/${trimprefix(id, "us.")}",
    ]
  ]))
  bedrock_model_arns = length(var.bedrock_model_arns) > 0 ? var.bedrock_model_arns : local.bedrock_arns_from_ids
}

resource "aws_iam_role" "runtime" {
  count = local.create_runtime ? 1 : 0
  name  = "${local.name_prefix}-agentcore"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "bedrock-agentcore.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

data "aws_iam_policy_document" "runtime" {
  count = local.create_runtime ? 1 : 0

  dynamic "statement" {
    for_each = length(local.bedrock_model_arns) > 0 ? [1] : []
    content {
      sid    = "InvokeAllowedBedrockModels"
      effect = "Allow"
      actions = [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:Converse",
        "bedrock:ConverseStream",
      ]
      resources = local.bedrock_model_arns
    }
  }

  statement {
    sid       = "DescribeAgentCoreLogGroups"
    effect    = "Allow"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["arn:${data.aws_partition.current.partition}:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:*"]
  }

  statement {
    sid       = "ManageAgentCoreRuntimeLogGroups"
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup", "logs:DescribeLogStreams"]
    resources = [local.agentcore_log_group_arn]
  }

  statement {
    sid       = "WriteAgentCoreRuntimeLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [local.agentcore_log_stream_arn]
  }

  statement {
    sid       = "ECRTokenAccess"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  dynamic "statement" {
    for_each = local.wire_observability ? [1] : []
    content {
      sid    = "AgentCoreXRay"
      effect = "Allow"
      actions = [
        "xray:PutTraceSegments",
        "xray:PutTelemetryRecords",
        "xray:GetSamplingRules",
        "xray:GetSamplingTargets",
      ]
      resources = ["*"]
    }
  }

  dynamic "statement" {
    for_each = local.wire_observability ? [1] : []
    content {
      sid       = "AgentCoreCloudWatchMetrics"
      effect    = "Allow"
      actions   = ["cloudwatch:PutMetricData"]
      resources = ["*"]
      condition {
        test     = "StringEquals"
        variable = "cloudwatch:namespace"
        values   = ["bedrock-agentcore"]
      }
    }
  }

  dynamic "statement" {
    for_each = local.ecr_repository_arn != "" ? [1] : []
    content {
      sid       = "PullConfiguredECRImage"
      effect    = "Allow"
      actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
      resources = [local.ecr_repository_arn]
    }
  }

  dynamic "statement" {
    for_each = var.serper_secret_arn != "" ? [1] : []
    content {
      sid       = "SerperSecretRead"
      effect    = "Allow"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [var.serper_secret_arn]
    }
  }
}

resource "aws_iam_role_policy" "runtime" {
  count = local.create_runtime ? 1 : 0
  name  = "${local.name_prefix}-agentcore"
  role  = aws_iam_role.runtime[0].id

  policy = data.aws_iam_policy_document.runtime[0].json
}

resource "aws_bedrockagentcore_agent_runtime" "this" {
  count              = local.create_runtime ? 1 : 0
  agent_runtime_name = local.runtime_name
  description        = "Vacation Planner CrewAI runtime"
  role_arn           = aws_iam_role.runtime[0].arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = var.container_uri
    }
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  environment_variables = merge(
    {
      AWS_REGION = data.aws_region.current.region
    },
    local.wire_observability ? {
      AGENT_OBSERVABILITY_ENABLED                        = "true"
      OTEL_PYTHON_DISTRO                                 = "aws_distro"
      OTEL_PYTHON_CONFIGURATOR                           = "aws_configurator"
      OTEL_EXPORTER_OTLP_PROTOCOL                        = "http/protobuf"
      OTEL_RESOURCE_ATTRIBUTES                           = "service.name=${local.runtime_name}"
      OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = "NO_CONTENT"
      UNIFIED_TRACES_DESTINATION_ENABLED                 = "true"
      CREWAI_DISABLE_TELEMETRY                           = "true"
    } : {},
    var.serper_secret_arn != "" ? {
      SERPER_SECRET_ARN = var.serper_secret_arn
    } : {}
  )

  depends_on = [aws_iam_role_policy.runtime]

  lifecycle {
    precondition {
      condition     = length(local.bedrock_model_arns) > 0
      error_message = "Set agent_bedrock_models (e.g. [\"us.amazon.nova-pro-v1:0\"]) or agent_allowed_bedrock_model_arns before enabling AgentCore."
    }

    precondition {
      condition     = local.ecr_repository_arn != ""
      error_message = "container_uri must be a standard ECR image URI so IAM can scope pull access to one repository."
    }
  }
}
