#!/usr/bin/env python3
"""Create trip + metrics tables against DynamoDB Local (or any endpoint).

Usage:
  docker compose up -d
  uv run python scripts/create_local_table.py

Env:
  DYNAMODB_ENDPOINT             default http://127.0.0.1:8000
  DYNAMODB_TABLE_NAME           default vacation-planner-local-table
  DYNAMODB_METRICS_TABLE_NAME   default vacation-planner-local-metrics
  AWS_REGION                    default us-east-1
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from db.client import (  # noqa: E402
    get_dynamodb_client,
    metrics_table_name,
    reset_clients,
    table_name,
)
from db.schema import ensure_metrics_table, ensure_table  # noqa: E402


def main() -> None:
    import os

    os.environ.setdefault("DYNAMODB_ENDPOINT", "http://127.0.0.1:8000")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "local")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "local")
    reset_clients()

    client = get_dynamodb_client()
    trip = table_name()
    metrics = metrics_table_name()
    ensure_table(client, trip, enable_ttl=False)
    ensure_metrics_table(client, metrics)
    endpoint = os.environ["DYNAMODB_ENDPOINT"]
    print(f"OK: table ready — {trip} @ {endpoint}")
    print(f"OK: metrics table ready — {metrics} @ {endpoint}")


if __name__ == "__main__":
    main()
