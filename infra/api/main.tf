data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

resource "random_password" "product_metrics_hash_pepper" {
  count   = var.product_metrics_hash_pepper == "" ? 1 : 0
  length  = 48
  special = false

  lifecycle {
    # Keep hashes stable across applies once generated.
    ignore_changes = [length, special, lower, upper, numeric, min_lower, min_upper, min_numeric, min_special, override_special]
  }
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  product_metrics_hash_pepper = (
    var.product_metrics_hash_pepper != ""
    ? var.product_metrics_hash_pepper
    : random_password.product_metrics_hash_pepper[0].result
  )
}

data "archive_file" "backend" {
  type        = "zip"
  source_dir  = var.backend_source_dir
  output_path = "${path.module}/.build/backend.zip"
}

resource "aws_iam_role" "lambda" {
  name = "${local.name_prefix}-api-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_app" {
  name = "${local.name_prefix}-api-app"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Sid      = "DynamoDB"
          Effect   = "Allow"
          Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"]
          Resource = [var.dynamodb_table_arn, "${var.dynamodb_table_arn}/index/*"]
        },
        {
          Sid    = "DynamoDBMetrics"
          Effect = "Allow"
          Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query"]
          Resource = [
            var.dynamodb_metrics_table_arn,
            "${var.dynamodb_metrics_table_arn}/index/*",
          ]
        },
        {
          Sid      = "SelfInvokePlanWorker"
          Effect   = "Allow"
          Action   = ["lambda:InvokeFunction"]
          Resource = "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:${local.name_prefix}-api"
        },
        {
          Sid      = "WriteOwnLogs"
          Effect   = "Allow"
          Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
          Resource = "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:${aws_cloudwatch_log_group.lambda.name}:*"
        }
      ],
      var.agent_runtime_arn != "" ? [
        {
          Sid      = "AgentCoreInvoke"
          Effect   = "Allow"
          Action   = ["bedrock-agentcore:InvokeAgentRuntime"]
          Resource = [var.agent_runtime_arn, "${var.agent_runtime_arn}/*"]
        }
      ] : [],
      # Least privilege: only when Lambda will call ApplyGuardrail (SAFETY_MODE=bedrock).
      contains(["bedrock", "guardrails"], var.safety_mode) && var.bedrock_guardrail_arn != "" ? [
        {
          Sid      = "BedrockApplyGuardrail"
          Effect   = "Allow"
          Action   = ["bedrock:ApplyGuardrail"]
          Resource = [var.bedrock_guardrail_arn]
        }
      ] : []
    )
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name_prefix}-api"
  retention_in_days = 7
}

resource "aws_lambda_function" "api" {
  function_name = "${local.name_prefix}-api"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  timeout       = 300
  memory_size   = 256

  filename         = data.archive_file.backend.output_path
  source_code_hash = data.archive_file.backend.output_base64sha256

  environment {
    variables = merge(
      {
        DYNAMODB_TABLE_NAME         = var.dynamodb_table_name
        DYNAMODB_METRICS_TABLE_NAME = var.dynamodb_metrics_table_name
        COGNITO_ISSUER              = var.cognito_issuer
        COGNITO_AUDIENCE            = var.cognito_user_pool_client_id
        AGENT_RUNTIME_ARN           = var.agent_runtime_arn
        AUTH_MODE                   = "cognito"
        CREW_MODE                   = "agentcore"
        SAFETY_MODE                 = var.safety_mode
        LOG_LEVEL                   = "INFO"
        BEDROCK_GUARDRAIL_ID        = var.bedrock_guardrail_id
        BEDROCK_GUARDRAIL_VERSION   = var.bedrock_guardrail_version
        PRODUCT_METRICS_HASH_PEPPER = local.product_metrics_hash_pepper
        METRICS_ADMIN_SUBS          = var.metrics_admin_subs
      },
      var.google_places_api_key != "" ? {
        GOOGLE_PLACES_API_KEY = var.google_places_api_key
      } : {}
    )
  }

  lifecycle {
    precondition {
      condition     = var.agent_runtime_arn != ""
      error_message = "API Lambda requires an AgentCore runtime ARN. Set enable_agentcore=true with a container URI and Bedrock model ARNs before apply."
    }
    precondition {
      condition = (
        !contains(["bedrock", "guardrails"], var.safety_mode)
        || (var.bedrock_guardrail_id != "" && var.bedrock_guardrail_arn != "")
      )
      error_message = "SAFETY_MODE=bedrock requires bedrock_guardrail_id and bedrock_guardrail_arn."
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda_app,
  ]
}

resource "aws_apigatewayv2_api" "http" {
  name          = "${local.name_prefix}-http"
  protocol_type = "HTTP"

  # HTTP API CORS: API Gateway answers OPTIONS when no OPTIONS+JWT route steals the request.
  cors_configuration {
    allow_headers = [
      "authorization",
      "content-type",
      "x-requested-with",
      "x-amz-date",
      "x-api-key",
    ]
    allow_methods  = ["GET", "POST", "PUT", "OPTIONS"]
    allow_origins  = ["*"]
    expose_headers = ["content-type"]
    max_age        = 86400
  }
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.http.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito"

  jwt_configuration {
    audience = [var.cognito_user_pool_client_id]
    issuer   = var.cognito_issuer
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

# Method-specific routes (not ANY): JWT must not apply to OPTIONS preflight.
locals {
  api_http_methods = ["GET", "POST", "PUT"]
}

resource "aws_apigatewayv2_route" "proxy" {
  for_each = toset(local.api_http_methods)

  api_id             = aws_apigatewayv2_api.http.id
  route_key          = "${each.value} /{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.lambda.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "root" {
  for_each = toset(local.api_http_methods)

  api_id             = aws_apigatewayv2_api.http.id
  route_key          = "${each.value} /"
  target             = "integrations/${aws_apigatewayv2_integration.lambda.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
  authorization_type = "JWT"
}

# Explicit unauthenticated OPTIONS so preflight never hits JWT (defense in depth).
resource "aws_apigatewayv2_route" "options_proxy" {
  api_id             = aws_apigatewayv2_api.http.id
  route_key          = "OPTIONS /{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.lambda.id}"
  authorization_type = "NONE"
}

resource "aws_apigatewayv2_route" "options_root" {
  api_id             = aws_apigatewayv2_api.http.id
  route_key          = "OPTIONS /"
  target             = "integrations/${aws_apigatewayv2_integration.lambda.id}"
  authorization_type = "NONE"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}
