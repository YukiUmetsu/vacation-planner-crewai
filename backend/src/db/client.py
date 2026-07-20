"""Endpoint-aware DynamoDB client factory."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import boto3


DEFAULT_TABLE_NAME = "vacation-planner-local-table"


def table_name() -> str:
    return os.getenv("DYNAMODB_TABLE_NAME", DEFAULT_TABLE_NAME)


def aws_region() -> str:
    return os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"


def dynamodb_endpoint() -> str | None:
    endpoint = os.getenv("DYNAMODB_ENDPOINT", "").strip()
    return endpoint or None


@lru_cache(maxsize=1)
def get_dynamodb_resource() -> Any:
    """boto3 DynamoDB resource (cached). Clear cache in tests via get_dynamodb_resource.cache_clear()."""
    kwargs: dict[str, Any] = {"region_name": aws_region()}
    endpoint = dynamodb_endpoint()
    if endpoint:
        kwargs["endpoint_url"] = endpoint
        kwargs["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID", "local")
        kwargs["aws_secret_access_key"] = os.getenv("AWS_SECRET_ACCESS_KEY", "local")
    return boto3.resource("dynamodb", **kwargs)


@lru_cache(maxsize=1)
def get_dynamodb_client() -> Any:
    kwargs: dict[str, Any] = {"region_name": aws_region()}
    endpoint = dynamodb_endpoint()
    if endpoint:
        kwargs["endpoint_url"] = endpoint
        kwargs["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID", "local")
        kwargs["aws_secret_access_key"] = os.getenv("AWS_SECRET_ACCESS_KEY", "local")
    return boto3.client("dynamodb", **kwargs)


def get_table(name: str | None = None) -> Any:
    """Return a boto3 Table resource for the vacation planner single-table."""
    return get_dynamodb_resource().Table(name or table_name())


def reset_clients() -> None:
    """Clear cached clients (call after env changes in tests)."""
    get_dynamodb_resource.cache_clear()
    get_dynamodb_client.cache_clear()
