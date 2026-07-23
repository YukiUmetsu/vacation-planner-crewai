"""Central DynamoDB value sanitization — floats must never reach boto3 serializers.

Use via ``SafeDynamoTable`` / ``get_table()`` for resource APIs, and
``serialize_dynamo_attr`` for low-level ``TypeSerializer`` / TransactWriteItems.
"""

from __future__ import annotations

from decimal import Decimal
import numbers
from typing import Any

DynamoItem = dict[str, Any]


def strip_nones(value: Any) -> Any:
    """Drop Nones and coerce non-integer reals to Decimal for DynamoDB."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, numbers.Real):
        return Decimal(str(value))
    if isinstance(value, (list, tuple, set)):
        return [strip_nones(v) for v in value if v is not None]
    if isinstance(value, dict):
        return {k: strip_nones(v) for k, v in value.items() if v is not None}
    return value


def assert_no_floats(value: Any, *, path: str = "$") -> None:
    """Fail fast with a path hint if any float survived cleaning."""
    if isinstance(value, float) and not isinstance(value, bool):
        raise TypeError(f"float at {path} must be Decimal before DynamoDB write")
    if isinstance(value, list):
        for i, item in enumerate(value):
            assert_no_floats(item, path=f"{path}[{i}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            assert_no_floats(item, path=f"{path}.{key}")


def prepare_dynamo_value(value: Any) -> Any:
    """Sanitize any value before a DynamoDB resource or low-level write."""
    cleaned = strip_nones(value)
    if cleaned is not None:
        assert_no_floats(cleaned)
    return cleaned


def prepare_dynamo_item(item: DynamoItem) -> DynamoItem:
    """Sanitize a full item map before ``put_item`` / ``update_item``."""
    cleaned = prepare_dynamo_value(item)
    if not isinstance(cleaned, dict):
        raise TypeError("DynamoDB item must be a mapping")
    return cleaned


def dynamo_safe_for_type_serializer(value: Any) -> Any:
    """Normalize for low-level ``TypeSerializer`` (never emit Python float).

    Whole-number Decimals become ``int``; fractional values stay ``Decimal``.
    """
    cleaned = prepare_dynamo_value(value)
    if cleaned is None:
        return None
    if isinstance(cleaned, bool):
        return cleaned
    if isinstance(cleaned, Decimal):
        if cleaned % 1 == 0:
            return int(cleaned)
        return cleaned
    if isinstance(cleaned, int):
        return cleaned
    if isinstance(cleaned, list):
        return [dynamo_safe_for_type_serializer(v) for v in cleaned]
    if isinstance(cleaned, dict):
        return {k: dynamo_safe_for_type_serializer(v) for k, v in cleaned.items()}
    return cleaned


def serialize_dynamo_attr(value: Any) -> dict[str, Any]:
    """TypeSerializer.encode after float→Decimal sanitize (TransactWriteItems path)."""
    from boto3.dynamodb.types import TypeSerializer

    return TypeSerializer().serialize(dynamo_safe_for_type_serializer(value))
