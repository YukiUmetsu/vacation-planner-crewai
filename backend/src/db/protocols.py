"""Structural types for DynamoDB clients used by this package."""

from __future__ import annotations

from typing import Any, Protocol


class Waiter(Protocol):
    def wait(self, *, TableName: str, **kwargs: Any) -> None: ...


class DynamoDBClientExceptions(Protocol):
    ValidationException: type[BaseException]
    TransactionCanceledException: type[BaseException]
    ConditionalCheckFailedException: type[BaseException]


class DynamoDBClient(Protocol):
    """Minimal boto3 DynamoDB client surface used by schema helpers."""

    exceptions: DynamoDBClientExceptions

    def list_tables(self) -> dict[str, Any]: ...

    def create_table(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_waiter(self, waiter_name: str) -> Waiter: ...

    def update_time_to_live(self, **kwargs: Any) -> dict[str, Any]: ...

    def transact_write_items(self, **kwargs: Any) -> dict[str, Any]: ...


class DynamoDBTable(Protocol):
    """Minimal boto3 DynamoDB Table resource surface used by the repository.

    boto3 returns plain dicts; numeric attributes may be ``Decimal``.
    """

    name: str

    def put_item(self, *, Item: dict[str, Any], **kwargs: Any) -> dict[str, Any]: ...

    def get_item(self, *, Key: dict[str, Any], **kwargs: Any) -> dict[str, Any]: ...

    def query(self, *, KeyConditionExpression: str, **kwargs: Any) -> dict[str, Any]: ...

    def update_item(
        self,
        *,
        Key: dict[str, Any],
        UpdateExpression: str,
        **kwargs: Any,
    ) -> dict[str, Any]: ...


class DynamoDBResource(Protocol):
    """Minimal boto3 DynamoDB resource (``boto3.resource('dynamodb')``)."""

    def Table(self, name: str) -> DynamoDBTable: ...
