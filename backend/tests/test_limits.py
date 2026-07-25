"""Limits: free-trip cap, GenAI quotas, admin bootstrap (ADR 006)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from db import keys
from handler import handler
from limits.admin import is_admin
from limits.genai import consume_genai_action
from limits.trips import assert_can_create_trip, max_trips_for_user


def _event(
    method: str,
    path: str,
    *,
    user: str = "user-a",
    email: str | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {"x-dev-user-sub": user}
    if email:
        headers["x-dev-user-email"] = email
    event: dict[str, Any] = {
        "requestContext": {"http": {"method": method, "path": path}},
        "rawPath": path,
        "headers": headers,
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _trip_body(**overrides: Any) -> dict[str, Any]:
    base = {
        "origin": "SFO",
        "destination": "Tokyo",
        "destination_type": "city",
        "start_date": "2026-09-01",
        "end_date": "2026-09-03",
        "preferences": "food",
    }
    base.update(overrides)
    return base


def test_max_trips_admin_unlimited() -> None:
    assert max_trips_for_user({"role": "admin", "plan": "free"}) is None


def test_assert_can_create_trip_blocks_second(monkeypatch: Any) -> None:
    monkeypatch.setenv("FREE_PLAN_MAX_TRIPS", "1")
    with pytest.raises(Exception) as exc:
        assert_can_create_trip(
            user_sub="u1",
            trip_count=1,
            profile={"role": "user", "plan": "free"},
        )
    assert exc.value.code == "free_trip_limit"  # type: ignore[attr-defined]


def test_create_trip_respects_free_limit(dynamodb_table: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("CREW_MODE", "fake")
    monkeypatch.setenv("SAFETY_MODE", "off")
    monkeypatch.setenv("FREE_PLAN_MAX_TRIPS", "1")
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.delenv("METRICS_ADMIN_SUBS", raising=False)

    first = handler(
        _event("POST", "/trips", body=_trip_body()),
        None,
    )
    assert first["statusCode"] == 201

    second = handler(
        _event("POST", "/trips", body=_trip_body(destination="Kyoto")),
        None,
    )
    assert second["statusCode"] == 403
    assert json.loads(second["body"])["code"] == "free_trip_limit"


def test_admin_email_bypasses_trip_limit(dynamodb_table: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("CREW_MODE", "fake")
    monkeypatch.setenv("SAFETY_MODE", "off")
    monkeypatch.setenv("FREE_PLAN_MAX_TRIPS", "1")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    monkeypatch.delenv("METRICS_ADMIN_SUBS", raising=False)

    for dest in ("Tokyo", "Kyoto"):
        resp = handler(
            _event(
                "POST",
                "/trips",
                user="admin-user",
                email="admin@example.com",
                body=_trip_body(destination=dest),
            ),
            None,
        )
        assert resp["statusCode"] == 201, resp.get("body")


def test_genai_hour_cap(dynamodb_table: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("GENAI_QUOTA", "on")
    monkeypatch.setenv("GENAI_CAP_HOUR", "2")
    monkeypatch.setenv("GENAI_CAP_DAY", "100")
    monkeypatch.setenv("CREW_MODE", "local")  # not fake — quotas apply
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.delenv("METRICS_ADMIN_SUBS", raising=False)

    profile = {"role": "user", "plan": "free"}
    consume_genai_action(user_sub="u-quota", profile=profile, table=dynamodb_table)
    consume_genai_action(user_sub="u-quota", profile=profile, table=dynamodb_table)
    with pytest.raises(Exception) as exc:
        consume_genai_action(user_sub="u-quota", profile=profile, table=dynamodb_table)
    assert getattr(exc.value, "code", None) == "genai_quota_exceeded"

    hour_sk = keys.usage_genai_hour_sk(
        datetime.now(timezone.utc).strftime("%Y%m%d%H")
    )
    item = dynamodb_table.get_item(
        Key={"pk": keys.user_pk("u-quota"), "sk": hour_sk}
    ).get("Item")
    assert item is not None
    assert int(item["count"]) == 2
    assert "expires_at" in item


def test_is_admin_from_profile_role() -> None:
    assert is_admin(profile={"role": "admin"})
    assert not is_admin(profile={"role": "user"})


def test_put_profile_strips_role(dynamodb_table: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("SAFETY_MODE", "off")
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.delenv("METRICS_ADMIN_SUBS", raising=False)

    resp = handler(
        _event(
            "PUT",
            "/profile",
            body={
                "display_name": "A",
                "preferences": "",
                "energy_level": 3,
                "interests": [],
                "visited_places": [],
                "role": "admin",
                "plan": "pro",
            },
        ),
        None,
    )
    assert resp["statusCode"] == 200
    profile = json.loads(resp["body"])["profile"]
    assert profile["role"] == "user"
    assert profile["plan"] == "free"


def test_metrics_admin_via_email(
    dynamodb_table: Any, metrics_table: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("ADMIN_EMAILS", "ops@example.com")
    monkeypatch.delenv("METRICS_ADMIN_SUBS", raising=False)
    resp = handler(
        _event("GET", "/admin/metrics/runs", user="ops", email="ops@example.com"),
        None,
    )
    assert resp["statusCode"] == 200
