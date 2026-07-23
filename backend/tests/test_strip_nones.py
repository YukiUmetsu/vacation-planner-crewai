"""SafeDynamoTable auto-sanitizes writes so floats never reach boto3."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

from boto3.dynamodb.types import TypeSerializer

from db.dynamo_sanitize import serialize_dynamo_attr
from db.repository import _assert_no_floats, _dynamo_safe, _strip_nones
from db.safe_table import SafeDynamoTable, ensure_safe_table


def test_strip_nones_converts_floats_to_decimal() -> None:
    cleaned = _strip_nones(
        {
            "name": "Senso-ji",
            "lat": 35.7148,
            "lng": 139.7967,
            "nested": {"score": 4.5},
            "tags": [1.0, "ok", None],
            "pair": (2.5, 3.5),
            "skip": None,
            "flag": True,
            "count": 3,
        }
    )
    assert cleaned["lat"] == Decimal("35.7148")
    assert cleaned["lng"] == Decimal("139.7967")
    assert cleaned["nested"]["score"] == Decimal("4.5")
    assert cleaned["tags"] == [Decimal("1.0"), "ok"]
    assert cleaned["pair"] == [Decimal("2.5"), Decimal("3.5")]
    assert cleaned["flag"] is True
    assert cleaned["count"] == 3
    assert "skip" not in cleaned
    assert isinstance(cleaned["lat"], Decimal)


def test_dynamo_safe_never_emits_python_floats() -> None:
    places = [
        {
            "name": "Senso-ji",
            "lat": 35.7148,
            "lng": 139.7967,
            "rating": 4.5,
            "nights": 2.0,
        }
    ]
    safe = _dynamo_safe(places)
    _assert_no_floats(safe)
    assert isinstance(safe[0]["lat"], Decimal)
    assert isinstance(safe[0]["rating"], Decimal)
    assert safe[0]["nights"] == 2
    assert not isinstance(safe[0]["nights"], float)

    serializer = TypeSerializer()
    encoded = serializer.serialize(safe)
    assert "L" in encoded


def test_serialize_dynamo_attr_accepts_raw_floats() -> None:
    encoded = serialize_dynamo_attr({"lat": 35.7148, "nights": 2.0})
    assert "M" in encoded
    assert encoded["M"]["lat"]["N"] == "35.7148"
    assert encoded["M"]["nights"]["N"] == "2"


def test_safe_table_put_item_coerces_floats_without_caller_prepare() -> None:
    """Future endpoints that skip prepare_* still cannot pass floats to DynamoDB."""
    inner = MagicMock()
    inner.name = "t"
    inner.put_item.return_value = {}
    table = SafeDynamoTable(inner)

    table.put_item(Item={"pk": "u", "lat": 35.7, "nested": {"score": 4.5}})

    written: dict[str, Any] = inner.put_item.call_args.kwargs["Item"]
    assert written["lat"] == Decimal("35.7")
    assert written["nested"]["score"] == Decimal("4.5")
    _assert_no_floats(written)


def test_safe_table_update_item_coerces_expression_values() -> None:
    inner = MagicMock()
    inner.name = "t"
    inner.update_item.return_value = {"Attributes": {}}
    table = ensure_safe_table(inner)

    table.update_item(
        Key={"pk": "u"},
        UpdateExpression="SET #p = :places",
        ExpressionAttributeNames={"#p": "places"},
        ExpressionAttributeValues={":places": [{"lat": 1.25}]},
    )

    values = inner.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert values[":places"][0]["lat"] == Decimal("1.25")
    _assert_no_floats(values)


def test_ensure_safe_table_is_idempotent() -> None:
    inner = MagicMock()
    once = ensure_safe_table(inner)
    twice = ensure_safe_table(once)
    assert once is twice
