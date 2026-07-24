"""Endpoint-aware DynamoDB client factory."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import boto3

from db.protocols import DynamoDBClient, DynamoDBResource, DynamoDBTable
from db.safe_table import ensure_safe_table


DEFAULT_TABLE_NAME = "vacation-planner-local-table"
DEFAULT_METRICS_TABLE_NAME = "vacation-planner-local-metrics"


def table_name() -> str:
    return os.getenv("DYNAMODB_TABLE_NAME", DEFAULT_TABLE_NAME)


def metrics_table_name() -> str:
    return os.getenv("DYNAMODB_METRICS_TABLE_NAME", DEFAULT_METRICS_TABLE_NAME)


def aws_region() -> str:
    return os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"


def dynamodb_endpoint() -> str | None:
    endpoint = os.getenv("DYNAMODB_ENDPOINT", "").strip()
    return endpoint or None


def _endpoint_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {"region_name": aws_region()}
    endpoint = dynamodb_endpoint()
    if endpoint:
        kwargs["endpoint_url"] = endpoint
        kwargs["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID", "local")
        kwargs["aws_secret_access_key"] = os.getenv("AWS_SECRET_ACCESS_KEY", "local")
    return kwargs


@lru_cache(maxsize=1)
def get_dynamodb_resource() -> DynamoDBResource:
    """boto3 DynamoDB resource (cached). Clear via reset_clients() after env changes."""
    return boto3.resource("dynamodb", **_endpoint_kwargs())


@lru_cache(maxsize=1)
def get_dynamodb_client() -> DynamoDBClient:
    return boto3.client("dynamodb", **_endpoint_kwargs())


def get_table(name: str | None = None) -> DynamoDBTable:
    """Return a sanitizing Table resource for the vacation planner single-table.

    Every ``put_item`` / ``update_item`` goes through float→Decimal coercion so
    new endpoints cannot regress the DynamoDB float TypeError.
    """
    raw = get_dynamodb_resource().Table(name or table_name())
    return ensure_safe_table(raw)


def get_metrics_table(name: str | None = None) -> DynamoDBTable:
    """Sanitizing Table for the dedicated offline-eval metrics table."""
    raw = get_dynamodb_resource().Table(name or metrics_table_name())
    return ensure_safe_table(raw)


def wrap_table(table: DynamoDBTable) -> DynamoDBTable:
    """Wrap an injected/test Table the same way as ``get_table()``."""
    return ensure_safe_table(table)


def reset_clients() -> None:
    """Clear cached clients (call after env changes in tests)."""
    get_dynamodb_resource.cache_clear()
    get_dynamodb_client.cache_clear()
