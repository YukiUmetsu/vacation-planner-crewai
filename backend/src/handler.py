"""API Gateway Lambda entry (stub)."""

from __future__ import annotations

from typing import Any


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return {
        "statusCode": 501,
        "headers": {"content-type": "application/json"},
        "body": '{"message":"Backend not implemented yet"}',
    }
