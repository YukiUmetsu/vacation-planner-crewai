#!/usr/bin/env python3
"""Create the single-table schema against DynamoDB Local (or any endpoint).

Usage:
  docker compose up -d
  uv run python scripts/create_local_table.py

Env:
  DYNAMODB_ENDPOINT   default http://127.0.0.1:8000
  DYNAMODB_TABLE_NAME default vacation-planner-local-table
  AWS_REGION          default us-east-1
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from db.client import get_dynamodb_client, reset_clients, table_name  # noqa: E402
from db.schema import ensure_table  # noqa: E402


def main() -> None:
    import os

    os.environ.setdefault("DYNAMODB_ENDPOINT", "http://127.0.0.1:8000")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "local")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "local")
    reset_clients()

    name = table_name()
    client = get_dynamodb_client()
    ensure_table(client, name, enable_ttl=False)
    print(f"OK: table ready — {name} @ {os.environ['DYNAMODB_ENDPOINT']}")


if __name__ == "__main__":
    main()
