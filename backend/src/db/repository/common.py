"""Shared types, errors, and table helpers for the repository package."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from db.client import get_table
from db.dynamo_sanitize import (
    assert_no_floats as _assert_no_floats,
    dynamo_safe_for_type_serializer as _dynamo_safe,
    prepare_dynamo_item,
    prepare_dynamo_value,
    strip_nones as _strip_nones,
)
from db.protocols import DynamoDBTable
from db.safe_table import ensure_safe_table

# DynamoDB item documents (keys + attributes). Numbers may be Decimal from boto3.
DynamoItem = dict[str, Any]


class ConcurrentModificationError(Exception):
    """Raised when a conditional DynamoDB write loses a race."""


class PersistenceError(Exception):
    """Unexpected DynamoDB/client failure (not an optimistic-lock conflict)."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_table(table: DynamoDBTable | None) -> DynamoDBTable:
    """Always return a SafeDynamoTable (covers injected moto tables in tests)."""
    return ensure_safe_table(table if table is not None else get_table())


def is_conditional_failure(exc: BaseException) -> bool:
    response = getattr(exc, "response", {}) or {}
    code = (response.get("Error") or {}).get("Code", "")
    return code == "ConditionalCheckFailedException" or "ConditionalCheckFailed" in type(
        exc
    ).__name__


# Private aliases kept for tests that imported them from ``db.repository``.
_now_iso = now_iso
_resolve_table = resolve_table
_is_conditional_failure = is_conditional_failure

__all__ = [
    "ConcurrentModificationError",
    "DynamoItem",
    "PersistenceError",
    "is_conditional_failure",
    "now_iso",
    "prepare_dynamo_item",
    "prepare_dynamo_value",
    "resolve_table",
    "_assert_no_floats",
    "_dynamo_safe",
    "_is_conditional_failure",
    "_now_iso",
    "_resolve_table",
    "_strip_nones",
]
