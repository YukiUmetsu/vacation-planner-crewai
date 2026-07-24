# Free-tier-friendly ops dashboard:
# - 2 custom metrics from API Lambda log filters (count toward the 10 custom-metric free tier)
# - Built-in AWS/Lambda + AWS/Bedrock-AgentCore metrics (do NOT count as custom)
# - 1 dashboard (free tier allows 3)

locals {
  api_logs_metric_namespace = local.name_prefix
  # ARN: arn:aws:bedrock-agentcore:region:acct:runtime/<runtime_id>
  agent_runtime_id = var.agent_runtime_arn != "" ? element(
    split("/", var.agent_runtime_arn),
    length(split("/", var.agent_runtime_arn)) - 1,
  ) : ""
  # Matches CloudWatch dimension Name on InvokeAgentRuntime (runtime_name::DEFAULT).
  agent_runtime_name_dim = "${replace("${local.name_prefix}_agent", "-", "_")}::DEFAULT"
  agent_log_group_name = local.agent_runtime_id != "" ? (
    "/aws/bedrock-agentcore/runtimes/${local.agent_runtime_id}-DEFAULT"
  ) : "(unset)"
}

# ---------------------------------------------------------------------------
# Custom metrics (API Lambda application logs)
# ---------------------------------------------------------------------------
# Python logging formats levels as "[ERROR]" / "[WARNING]" on CloudWatch.
#
# LambdaErrors ([ERROR]) typically means:
#   - HTTP 5xx ApiError responses (handler logs API_ERROR + API_ERROR_JSON at ERROR)
#   - Unhandled exceptions / Tracebacks (logger.exception) e.g. DynamoDB AccessDenied,
#     plan_next_day worker crashes while a claim is held
#   - Other logger.error calls
# Does NOT include Lambda platform "Errors" (those are AWS/Lambda Errors below).
#
# LambdaWarnings ([WARNING]) typically means:
#   - HTTP 4xx ApiError responses (auth, validation, not found) — still tagged API_ERROR*
#   - Soft / degraded failures that returned success or a controlled error:
#       Places enrich/search failures, Secrets Manager fetch misses,
#       AgentCore client transport warnings (source=agentcore)
# These are "something went wrong but the process kept going" signals.

resource "aws_cloudwatch_log_metric_filter" "lambda_errors" {
  name           = "${local.name_prefix}-api-log-errors"
  log_group_name = aws_cloudwatch_log_group.lambda.name
  pattern        = "\"[ERROR]\""

  metric_transformation {
    name          = "LambdaErrors"
    namespace     = local.api_logs_metric_namespace
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_log_metric_filter" "lambda_warnings" {
  name           = "${local.name_prefix}-api-log-warnings"
  log_group_name = aws_cloudwatch_log_group.lambda.name
  pattern        = "\"[WARNING]\""

  metric_transformation {
    name          = "LambdaWarnings"
    namespace     = local.api_logs_metric_namespace
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_dashboard" "api_logs" {
  dashboard_name = "${local.name_prefix}-api-logs"

  # API module always requires agent_runtime_arn, so AgentCore widgets are always present.
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 5
        properties = {
          markdown = join("\n", [
            "## ${local.name_prefix} ops — API Lambda + AgentCore",
            "",
            "### API Lambda log metrics (custom)",
            "| Metric | Filter | What it usually means |",
            "| --- | --- | --- |",
            "| **LambdaErrors** | `[ERROR]` in `${aws_cloudwatch_log_group.lambda.name}` | **Server-side failures**: HTTP **5xx** (`API_ERROR` / `API_ERROR_JSON`), unhandled exceptions / Tracebacks (e.g. DynamoDB IAM, worker crash). Investigate these first. |",
            "| **LambdaWarnings** | `[WARNING]` in same group | **Client / soft failures**: HTTP **4xx** ApiErrors (auth, validation, not found), Places enrich/search misses, secret fetch warnings, AgentCore client warnings. Spikes may be noisy (bad clients) or real degradation. |",
            "",
            "Drill-down: Logs Insights on that log group → `filter @message like /API_ERROR/` (add `status=5` for 5xx only). Match browser `x-amzn-requestid` to `@requestId`.",
            "",
            "### AgentCore (built-in `AWS/Bedrock-AgentCore` — free)",
            "Runtime `${local.agent_runtime_id}` · logs `${local.agent_log_group_name}` · GenAI Observability console for traces/sessions.",
            "| Metric | Meaning |",
            "| --- | --- |",
            "| **Invocations** | Agent runtime invoke calls from the API/worker. |",
            "| **Errors** | Failed invokes (platform aggregate). |",
            "| **SystemErrors** | Service-side failures (5xx-class). |",
            "| **UserErrors** | Client-side failures (4xx-class, e.g. bad payload) — not throttles. |",
            "| **Throttles** | 429 / capacity limits. |",
            "| **Latency** | End-to-end invoke time (request received → final response), ms. |",
            "| **Duration** | Separate runtime duration series (also ms); compare with Latency when diagnosing slow crews. |",
            "",
            "App-level crew crashes also log `crew_failed` + Traceback in the agent log group (Logs Insights). Prefer GenAI Observability for span/token detail.",
          ])
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 5
        width  = 6
        height = 4
        properties = {
          title  = "API [ERROR] logs (5m sum)"
          region = data.aws_region.current.region
          view   = "singleValue"
          period = 300
          stat   = "Sum"
          metrics = [
            [local.api_logs_metric_namespace, "LambdaErrors"],
          ]
        }
      },
      {
        type   = "metric"
        x      = 6
        y      = 5
        width  = 6
        height = 4
        properties = {
          title  = "API [WARNING] logs (5m sum)"
          region = data.aws_region.current.region
          view   = "singleValue"
          period = 300
          stat   = "Sum"
          metrics = [
            [local.api_logs_metric_namespace, "LambdaWarnings"],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 5
        width  = 6
        height = 4
        properties = {
          title  = "Lambda platform Errors (5m)"
          region = data.aws_region.current.region
          view   = "singleValue"
          period = 300
          stat   = "Sum"
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.api.function_name],
          ]
        }
      },
      {
        type   = "metric"
        x      = 18
        y      = 5
        width  = 6
        height = 4
        properties = {
          title  = "Lambda Throttles (5m)"
          region = data.aws_region.current.region
          view   = "singleValue"
          period = 300
          stat   = "Sum"
          metrics = [
            ["AWS/Lambda", "Throttles", "FunctionName", aws_lambda_function.api.function_name],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 9
        width  = 12
        height = 6
        properties = {
          title   = "API log ERROR vs WARNING"
          region  = data.aws_region.current.region
          view    = "timeSeries"
          stacked = false
          period  = 300
          stat    = "Sum"
          yAxis = {
            left = { min = 0 }
          }
          metrics = [
            [local.api_logs_metric_namespace, "LambdaErrors", { label = "[ERROR] 5xx / exceptions" }],
            [".", "LambdaWarnings", { label = "[WARNING] 4xx / soft fails" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 9
        width  = 12
        height = 6
        properties = {
          title   = "Lambda duration / errors (platform)"
          region  = data.aws_region.current.region
          view    = "timeSeries"
          stacked = false
          period  = 300
          yAxis = {
            left = { min = 0 }
          }
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.api.function_name, { stat = "p99", label = "Duration p99 (ms)" }],
            [".", "Errors", ".", ".", { stat = "Sum", label = "Platform Errors", yAxis = "right" }],
          ]
        }
      },
      {
        type   = "text"
        x      = 0
        y      = 15
        width  = 24
        height = 1
        properties = {
          markdown = "### AgentCore runtime `${local.agent_runtime_id}`"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 16
        width  = 6
        height = 4
        properties = {
          title  = "Agent Invocations (5m)"
          region = data.aws_region.current.region
          view   = "singleValue"
          period = 300
          stat   = "Sum"
          metrics = [
            ["AWS/Bedrock-AgentCore", "Invocations", "Resource", var.agent_runtime_arn, "Operation", "InvokeAgentRuntime", "Name", local.agent_runtime_name_dim],
          ]
        }
      },
      {
        type   = "metric"
        x      = 6
        y      = 16
        width  = 6
        height = 4
        properties = {
          title  = "Agent Errors (5m)"
          region = data.aws_region.current.region
          view   = "singleValue"
          period = 300
          stat   = "Sum"
          metrics = [
            ["AWS/Bedrock-AgentCore", "Errors", "Resource", var.agent_runtime_arn, "Operation", "InvokeAgentRuntime", "Name", local.agent_runtime_name_dim],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 16
        width  = 6
        height = 4
        properties = {
          title  = "Agent SystemErrors (5m)"
          region = data.aws_region.current.region
          view   = "singleValue"
          period = 300
          stat   = "Sum"
          metrics = [
            ["AWS/Bedrock-AgentCore", "SystemErrors", "Resource", var.agent_runtime_arn, "Operation", "InvokeAgentRuntime", "Name", local.agent_runtime_name_dim],
          ]
        }
      },
      {
        type   = "metric"
        x      = 18
        y      = 16
        width  = 6
        height = 4
        properties = {
          title  = "Agent UserErrors (5m)"
          region = data.aws_region.current.region
          view   = "singleValue"
          period = 300
          stat   = "Sum"
          metrics = [
            ["AWS/Bedrock-AgentCore", "UserErrors", "Resource", var.agent_runtime_arn, "Operation", "InvokeAgentRuntime", "Name", local.agent_runtime_name_dim],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 20
        width  = 12
        height = 6
        properties = {
          title   = "Agent invoke volume & failures"
          region  = data.aws_region.current.region
          view    = "timeSeries"
          stacked = false
          period  = 300
          stat    = "Sum"
          yAxis = {
            left = { min = 0 }
          }
          metrics = [
            ["AWS/Bedrock-AgentCore", "Invocations", "Resource", var.agent_runtime_arn, "Operation", "InvokeAgentRuntime", "Name", local.agent_runtime_name_dim, { label = "Invocations" }],
            [".", "SystemErrors", ".", ".", ".", ".", ".", ".", { label = "SystemErrors (5xx)" }],
            [".", "UserErrors", ".", ".", ".", ".", ".", ".", { label = "UserErrors (4xx)" }],
            [".", "Throttles", ".", ".", ".", ".", ".", ".", { label = "Throttles" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 20
        width  = 12
        height = 6
        properties = {
          title   = "Agent Latency / Duration (ms)"
          region  = data.aws_region.current.region
          view    = "timeSeries"
          stacked = false
          period  = 300
          yAxis = {
            left = { min = 0 }
          }
          metrics = [
            ["AWS/Bedrock-AgentCore", "Latency", "Resource", var.agent_runtime_arn, "Operation", "InvokeAgentRuntime", "Name", local.agent_runtime_name_dim, { stat = "p99", label = "Latency p99" }],
            [".", "Duration", ".", ".", ".", ".", ".", ".", { stat = "p99", label = "Duration p99" }],
            [".", "Latency", ".", ".", ".", ".", ".", ".", { stat = "Average", label = "Latency avg" }],
          ]
        }
      },
    ]
  })
}
