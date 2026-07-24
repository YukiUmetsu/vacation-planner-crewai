# Observability (Transaction Search)

Account/region prerequisites for CloudWatch GenAI Observability.

## Resources

- `aws_cloudwatch_log_resource_policy.transaction_search` — X-Ray → CloudWatch Logs (`aws/spans`, Application Signals, AgentCore runtime log groups). This is the account-level write grant; the AgentCore execution role does not need `logs:PutResourcePolicy`.
- `awscc_xray_transaction_search_config.this` — enables Transaction Search + indexing %

AgentCore runtime (in `../agentcore/main.tf` when observability is on):

- `aws_cloudwatch_log_delivery_source` (`TRACES`) + XRAY destination + delivery — required for GenAI Observability **Agents** view

These Transaction Search settings are **account+region singletons**. Enable via root `enable_genai_observability` in only one stack per region.

## Import (if already enabled)

```bash
terraform import 'module.observability.awscc_xray_transaction_search_config.this[0]' <ACCOUNT_ID>
terraform import 'module.observability.aws_cloudwatch_log_resource_policy.transaction_search[0]' VacationPlannerTransactionSearchXRay
```
