"""Profile API + persistence tests."""

from __future__ import annotations

import json
from typing import Any

import pytest

from handler import handler
from routes import profile as profile_routes
from services.profile_service import ProfileService
from services.safety import NoopSafetyGate


def _event(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    user: str = "profile-user",
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "requestContext": {"http": {"method": method}},
        "rawPath": path,
        "headers": {"x-dev-user-sub": user},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


@pytest.fixture()
def wired_profile(dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch):
    service = ProfileService(table=dynamodb_table, safety=NoopSafetyGate())

    def _svc(**_kwargs: Any) -> ProfileService:
        return service

    monkeypatch.setattr(profile_routes, "_service", _svc)
    monkeypatch.setenv("AUTH_MODE", "dev")
    return service


def test_get_profile_defaults(wired_profile: ProfileService) -> None:
    resp = handler(_event("GET", "/profile"))
    assert resp["statusCode"] == 404
    body = json.loads(resp["body"])
    assert body["code"] == "not_found"


def test_get_profile_defaults_for_planning(wired_profile: ProfileService) -> None:
    profile = wired_profile.get_profile("profile-user")
    assert profile["energy_level"] == 3
    assert profile["max_comfortable_minutes"] == 510
    assert profile["interests"] == []


def test_put_and_get_profile(wired_profile: ProfileService) -> None:
    put = handler(
        _event(
            "PUT",
            "/profile",
            body={
                "display_name": "Yuki",
                "preferences": "slow travel",
                "energy_level": 2,
                "interests": ["temples", "food"],
                "visited_places": [{"name": "Senso-ji", "city": "Tokyo"}],
            },
        )
    )
    assert put["statusCode"] == 200
    saved = json.loads(put["body"])["profile"]
    assert saved["display_name"] == "Yuki"
    assert saved["energy_level"] == 2
    assert saved["max_comfortable_minutes"] == 390

    got = handler(_event("GET", "/profile"))
    profile = json.loads(got["body"])["profile"]
    assert profile["preferences"] == "slow travel"
    assert profile["interests"] == ["temples", "food"]
    assert profile["visited_places"][0]["name"] == "Senso-ji"


def test_list_trips_ignores_profile_row(
    dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from crews.fake_runner import FakeCrewRunner
    from routes import trips as trip_routes
    from services.trip_service import TripService

    trip_svc = TripService(
        table=dynamodb_table,
        runner=FakeCrewRunner(),
        safety=NoopSafetyGate(),
    )
    profile_svc = ProfileService(table=dynamodb_table, safety=NoopSafetyGate())

    monkeypatch.setattr(trip_routes, "_service", lambda **_: trip_svc)
    monkeypatch.setattr(profile_routes, "_service", lambda **_: profile_svc)
    monkeypatch.setenv("AUTH_MODE", "dev")

    profile_svc.put_profile(
        "profile-user",
        {
            "display_name": "Yuki",
            "preferences": "",
            "energy_level": 3,
            "interests": [],
            "visited_places": [],
        },
    )
    create = handler(
        _event(
            "POST",
            "/trips",
            body={
                "origin": "NYC",
                "destination": "Tokyo",
                "destination_type": "city",
                "start_date": "2026-09-01",
                "end_date": "2026-09-03",
            },
        )
    )
    assert create["statusCode"] == 201
    listed = handler(_event("GET", "/trips"))
    trips = json.loads(listed["body"])["trips"]
    assert len(trips) == 1
    assert all(t.get("entity_type") != "PROFILE" for t in trips)
