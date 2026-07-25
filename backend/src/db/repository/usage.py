"""Atomic GenAI usage counters (hour/day buckets with TTL)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from botocore.exceptions import ClientError

from db import keys
from db.protocols import DynamoDBTable
from db.repository.common import resolve_table

Window = Literal["hour", "day"]


class QuotaExceeded(Exception):
    def __init__(self, window: Window) -> None:
        super().__init__(window)
        self.window = window


def _increment_bucket(
    *,
    user_sub: str,
    sk: str,
    cap: int,
    expires_at: int,
    table: DynamoDBTable,
) -> None:
    if cap <= 0:
        raise QuotaExceeded("hour" if "HOUR" in sk else "day")
    try:
        table.update_item(
            Key={"pk": keys.user_pk(user_sub), "sk": sk},
            UpdateExpression=(
                "ADD #c :one SET entity_type = if_not_exists(entity_type, :et), "
                "expires_at = if_not_exists(expires_at, :exp), "
                "updated_at = :now"
            ),
            ConditionExpression="attribute_not_exists(#c) OR #c < :cap",
            ExpressionAttributeNames={"#c": "count"},
            ExpressionAttributeValues={
                ":one": 1,
                ":cap": cap,
                ":et": "USAGE",
                ":exp": expires_at,
                ":now": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise QuotaExceeded("hour" if "HOUR" in sk else "day") from exc
        raise


def try_consume_genai_windows(
    *,
    user_sub: str,
    now: datetime,
    hour_cap: int,
    day_cap: int,
    table: DynamoDBTable | None = None,
) -> None:
    """Increment hour then day. On day failure after hour success, still over — rare."""
    tbl = resolve_table(table)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    hour_key = now.strftime("%Y%m%d%H")
    day_key = now.strftime("%Y%m%d")
    # Grace past bucket end so TTL does not drop the active counter early.
    hour_exp = int((now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=3)).timestamp())
    day_exp = int((now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=2)).timestamp())

    _increment_bucket(
        user_sub=user_sub,
        sk=keys.usage_genai_hour_sk(hour_key),
        cap=hour_cap,
        expires_at=hour_exp,
        table=tbl,
    )
    try:
        _increment_bucket(
            user_sub=user_sub,
            sk=keys.usage_genai_day_sk(day_key),
            cap=day_cap,
            expires_at=day_exp,
            table=tbl,
        )
    except QuotaExceeded:
        # Hour already consumed; day blocked. Accept slight hour skew vs perfect rollback.
        raise
