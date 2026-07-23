"""Table wrapper that sanitizes every resource write (put/update).

New endpoints that call ``get_table().put_item(...)`` or pass a table into the
repository automatically get float→Decimal coercion — no per-call ``prepare_*``.
"""

from __future__ import annotations

from typing import Any

from db.dynamo_sanitize import prepare_dynamo_item, prepare_dynamo_value
from db.protocols import DynamoDBTable


class SafeDynamoTable:
    """Delegates to a boto3 Table; sanitizes ``Item`` / ``ExpressionAttributeValues``."""

    __slots__ = ("_inner",)

    def __init__(self, inner: DynamoDBTable) -> None:
        self._inner = inner

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def meta(self) -> Any:
        return getattr(self._inner, "meta", None)

    def put_item(self, *, Item: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return self._inner.put_item(Item=prepare_dynamo_item(Item), **kwargs)

    def get_item(self, *, Key: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return self._inner.get_item(Key=Key, **kwargs)

    def query(self, *, KeyConditionExpression: str, **kwargs: Any) -> dict[str, Any]:
        return self._inner.query(
            KeyConditionExpression=KeyConditionExpression, **kwargs
        )

    def update_item(
        self,
        *,
        Key: dict[str, Any],
        UpdateExpression: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        values = kwargs.get("ExpressionAttributeValues")
        if isinstance(values, dict):
            kwargs = {
                **kwargs,
                "ExpressionAttributeValues": {
                    k: prepare_dynamo_value(v) for k, v in values.items()
                },
            }
        return self._inner.update_item(
            Key=Key, UpdateExpression=UpdateExpression, **kwargs
        )

    def delete_item(self, *, Key: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return self._inner.delete_item(Key=Key, **kwargs)

    def __getattr__(self, name: str) -> Any:
        # Forward batch_writer, scan, etc. without inventing unsanitized writes.
        return getattr(self._inner, name)


def ensure_safe_table(table: DynamoDBTable) -> SafeDynamoTable:
    """Idempotent wrap — safe to call on already-wrapped tables."""
    if isinstance(table, SafeDynamoTable):
        return table
    return SafeDynamoTable(table)
