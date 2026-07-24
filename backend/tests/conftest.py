"""Pytest fixtures: moto-backed DynamoDB tables."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from db.client import reset_clients
from db.schema import ensure_metrics_table, ensure_table


@pytest.fixture(autouse=True)
def _dev_auth_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests use forgeable identity; production default remains cognito."""
    monkeypatch.setenv("AUTH_MODE", "dev")


@pytest.fixture()
def dynamodb_table(monkeypatch: pytest.MonkeyPatch):
    """Create the vacation planner table in moto; yield a boto3 Table resource."""
    table_name = "vacation-planner-test-table"
    monkeypatch.setenv("DYNAMODB_TABLE_NAME", table_name)
    monkeypatch.delenv("DYNAMODB_ENDPOINT", raising=False)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    reset_clients()

    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        ensure_table(client, table_name, enable_ttl=True)
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        table = resource.Table(table_name)
        yield table
        reset_clients()


@pytest.fixture()
def metrics_table(monkeypatch: pytest.MonkeyPatch):
    """Create the dedicated metrics table in moto; yield a boto3 Table resource."""
    table_name = "vacation-planner-test-metrics"
    monkeypatch.setenv("DYNAMODB_METRICS_TABLE_NAME", table_name)
    monkeypatch.delenv("DYNAMODB_ENDPOINT", raising=False)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    reset_clients()

    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        ensure_metrics_table(client, table_name)
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        table = resource.Table(table_name)
        yield table
        reset_clients()
