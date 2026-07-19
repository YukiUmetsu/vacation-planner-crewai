data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  name_prefix    = "${var.project_name}-${var.environment}"
  create_runtime = var.enabled && var.container_uri != ""
  # Agent runtime names: letters, numbers, underscore
  runtime_name = replace("${local.name_prefix}_agent", "-", "_")
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
    Statement = [
      {
        Sid    = "BedrockInvoke"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:Converse",
          "bedrock:ConverseStream",
        ]
        Resource = "*"
      },
      {
        Sid    = "Logs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams",
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        Sid      = "ECRPull"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
        Resource = "*"
      },
    ]
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
}
