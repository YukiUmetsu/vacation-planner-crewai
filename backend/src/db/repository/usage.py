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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _increment_bucket(
    *,
    user_sub: str,
    sk: str,
    cap: int,
    expires_at: int,
    table: DynamoDBTable,
) -> None:
    window: Window = "hour" if "HOUR" in sk else "day"
    if cap <= 0:
        raise QuotaExceeded(window)
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
                ":now": _now_iso(),
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise QuotaExceeded(window) from exc
        raise


def _decrement_bucket(
    *,
    user_sub: str,
    sk: str,
    table: DynamoDBTable,
) -> None:
    """Best-effort undo of a prior ADD (compensate failed multi-window consume)."""
    try:
        table.update_item(
            Key={"pk": keys.user_pk(user_sub), "sk": sk},
            UpdateExpression="ADD #c :neg SET updated_at = :now",
            ConditionExpression="attribute_exists(#c) AND #c > :zero",
            ExpressionAttributeNames={"#c": "count"},
            ExpressionAttributeValues={
                ":neg": -1,
                ":zero": 0,
                ":now": _now_iso(),
            },
        )
    except ClientError:
        # Do not mask the original QuotaExceeded; compensation is best-effort.
        return


def try_consume_genai_windows(
    *,
    user_sub: str,
    now: datetime,
    hour_cap: int,
    day_cap: int,
    table: DynamoDBTable | None = None,
) -> None:
    """Increment hour and day atomically-enough: compensate hour if day rejects."""
    tbl = resolve_table(table)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    hour_key = now.strftime("%Y%m%d%H")
    day_key = now.strftime("%Y%m%d")
    hour_sk = keys.usage_genai_hour_sk(hour_key)
    day_sk = keys.usage_genai_day_sk(day_key)
    # Grace past bucket end so TTL does not drop the active counter early.
    hour_exp = int(
        (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=3)).timestamp()
    )
    day_exp = int(
        (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=2)).timestamp()
    )

    _increment_bucket(
        user_sub=user_sub,
        sk=hour_sk,
        cap=hour_cap,
        expires_at=hour_exp,
        table=tbl,
    )
    try:
        _increment_bucket(
            user_sub=user_sub,
            sk=day_sk,
            cap=day_cap,
            expires_at=day_exp,
            table=tbl,
        )
    except Exception:
        # QuotaExceeded or transient Dynamo errors — undo hour so counters stay paired.
        _decrement_bucket(user_sub=user_sub, sk=hour_sk, table=tbl)
        raise


def refund_genai_windows(
    *,
    user_sub: str,
    now: datetime | None = None,
    table: DynamoDBTable | None = None,
) -> None:
    """Best-effort undo of the latest hour+day consume (enqueue failure path)."""
    tbl = resolve_table(table)
    when = now or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    else:
        when = when.astimezone(timezone.utc)
    _decrement_bucket(
        user_sub=user_sub,
        sk=keys.usage_genai_hour_sk(when.strftime("%Y%m%d%H")),
        table=tbl,
    )
    _decrement_bucket(
        user_sub=user_sub,
        sk=keys.usage_genai_day_sk(when.strftime("%Y%m%d")),
        table=tbl,
    )
