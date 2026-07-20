"""Structural types for DynamoDB clients used by this package."""

from __future__ import annotations

from typing import Any, Protocol


class Waiter(Protocol):
    def wait(self, **kwargs: Any) -> None: ...


class DynamoDBClientExceptions(Protocol):
    ValidationException: type[BaseException]


class DynamoDBClient(Protocol):
    """Minimal boto3 DynamoDB client surface used by schema helpers."""

    exceptions: DynamoDBClientExceptions

    def list_tables(self) -> dict[str, Any]: ...

    def create_table(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_waiter(self, waiter_name: str) -> Waiter: ...

    def update_time_to_live(self, **kwargs: Any) -> dict[str, Any]: ...
