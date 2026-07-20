"""Single-table DynamoDB schema — keep in sync with infra/dynamodb/main.tf."""

from __future__ import annotations

from typing import Any

from db.protocols import DynamoDBClient

GSI1_NAME = "gsi1"
TTL_ATTRIBUTE = "expires_at"


def table_definition(table_name: str) -> dict[str, Any]:
    """boto3 create_table kwargs matching Terraform."""
    return {
        "TableName": table_name,
        "BillingMode": "PAY_PER_REQUEST",
        "AttributeDefinitions": [
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
            {"AttributeName": "gsi1pk", "AttributeType": "S"},
            {"AttributeName": "gsi1sk", "AttributeType": "S"},
        ],
        "KeySchema": [
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": GSI1_NAME,
                "KeySchema": [
                    {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                    {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    }


def ensure_table(dynamodb_client: DynamoDBClient, table_name: str, *, enable_ttl: bool = True) -> str:
    """Create the table if it does not exist. Returns table_name."""
    existing = dynamodb_client.list_tables().get("TableNames", [])
    if table_name not in existing:
        dynamodb_client.create_table(**table_definition(table_name))
        waiter = dynamodb_client.get_waiter("table_exists")
        waiter.wait(TableName=table_name)

    if enable_ttl:
        try:
            dynamodb_client.update_time_to_live(
                TableName=table_name,
                TimeToLiveSpecification={
                    "Enabled": True,
                    "AttributeName": TTL_ATTRIBUTE,
                },
            )
        except dynamodb_client.exceptions.ValidationException:
            # Already enabled / Local quirks — ignore
            pass
        except Exception:
            # DynamoDB Local sometimes rejects TTL; schema still usable without it
            pass

    return table_name
