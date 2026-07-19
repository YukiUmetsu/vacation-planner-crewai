data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  name_prefix    = "${var.project_name}-${var.environment}"
  create_runtime = var.enabled
  # Agent runtime names: letters, numbers, underscore
  runtime_name = replace("${local.name_prefix}_agent", "-", "_")

  ecr_image_parts     = local.create_runtime && can(regex("^([0-9]{12})\\.dkr\\.ecr\\.([a-z0-9-]+)\\.[^/]+/(.+)$", var.container_uri)) ? regex("^([0-9]{12})\\.dkr\\.ecr\\.([a-z0-9-]+)\\.[^/]+/(.+)$", var.container_uri) : []
  ecr_repository_name = length(local.ecr_image_parts) == 3 ? regexreplace(local.ecr_image_parts[2], "([@:]).*$", "") : ""
  ecr_repository_arn  = local.ecr_repository_name != "" ? "arn:${data.aws_partition.current.partition}:ecr:${local.ecr_image_parts[1]}:${local.ecr_image_parts[0]}:repository/${local.ecr_repository_name}" : ""

  agentcore_log_group_arn  = "arn:${data.aws_partition.current.partition}:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
  agentcore_log_stream_arn = "${local.agentcore_log_group_arn}:log-stream:*"
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

resource "aws_iam_role_policy" "runtime" {
  count = local.create_runtime ? 1 : 0
  name  = "${local.name_prefix}-agentcore"
  role  = aws_iam_role.runtime[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      length(var.bedrock_model_arns) > 0 ? [
        {
          Sid    = "InvokeAllowedBedrockModels"
          Effect = "Allow"
          Action = [
            "bedrock:InvokeModel",
            "bedrock:InvokeModelWithResponseStream",
            "bedrock:Converse",
            "bedrock:ConverseStream",
          ]
          Resource = var.bedrock_model_arns
        }
      ] : [],
      [
        {
          Sid      = "DescribeAgentCoreLogGroups"
          Effect   = "Allow"
          Action   = ["logs:DescribeLogGroups"]
          Resource = "arn:${data.aws_partition.current.partition}:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:*"
        },
        {
          Sid    = "ManageAgentCoreRuntimeLogGroups"
          Effect = "Allow"
          Action = [
            "logs:CreateLogGroup",
            "logs:DescribeLogStreams",
          ]
          Resource = local.agentcore_log_group_arn
        },
        {
          Sid    = "WriteAgentCoreRuntimeLogs"
          Effect = "Allow"
          Action = [
            "logs:CreateLogStream",
            "logs:PutLogEvents",
          ]
          Resource = local.agentcore_log_stream_arn
        },
        {
          Sid      = "ECRTokenAccess"
          Effect   = "Allow"
          Action   = ["ecr:GetAuthorizationToken"]
          Resource = "*"
        },
      ],
      local.ecr_repository_arn != "" ? [
        {
          Sid      = "PullConfiguredECRImage"
          Effect   = "Allow"
          Action   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
          Resource = local.ecr_repository_arn
        }
      ] : []
    )
  })
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
    var.serper_api_key != "" ? {
      SERPER_API_KEY = var.serper_api_key
    } : {}
  )

  depends_on = [aws_iam_role_policy.runtime]

  lifecycle {
    precondition {
      condition     = length(var.bedrock_model_arns) > 0
      error_message = "Set bedrock_model_arns to the exact Bedrock model or inference profile ARNs before enabling AgentCore."
    }

    precondition {
      condition     = local.ecr_repository_arn != ""
      error_message = "container_uri must be a standard ECR image URI so IAM can scope pull access to one repository."
    }
  }
}
