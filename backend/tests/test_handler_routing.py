"""Handler routing + AUTH_MODE=dev."""

from __future__ import annotations

import json
from typing import Any

import pytest

from crews.fake_runner import FakeCrewRunner
from handler import handler
from services.safety import NoopSafetyGate
from services.trip_service import TripService
from routes import trips as trip_routes


def _event(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    user: str = "handler-user",
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
def wired(dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch):
    service = TripService(
        table=dynamodb_table,
        runner=FakeCrewRunner(),
        safety=NoopSafetyGate(),
    )

    def _svc(**_kwargs: Any) -> TripService:
        return service

    monkeypatch.setattr(trip_routes, "_service", _svc)
    monkeypatch.setenv("AUTH_MODE", "dev")
    return service


def test_create_and_list(wired: TripService) -> None:
    create = handler(
        _event(
            "POST",
            "/trips",
            body={
                "origin": "Chicago",
                "destination": "Japan",
                "destination_type": "country",
                "start_date": "2026-09-01",
                "end_date": "2026-09-07",
            },
        )
    )
    assert create["statusCode"] == 201
    payload = json.loads(create["body"])
    trip_id = payload["trip"]["trip_id"]

    listed = handler(_event("GET", "/trips"))
    assert listed["statusCode"] == 200
    trips = json.loads(listed["body"])["trips"]
    assert any(t["trip_id"] == trip_id for t in trips)


def test_unknown_route() -> None:
    resp = handler(_event("GET", "/nope"))
    assert resp["statusCode"] == 404


def test_dev_auth_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    from auth import get_user_sub

    assert get_user_sub({"headers": {"X-Dev-User-Sub": "abc"}}) == "abc"


def test_suggest_place_route(wired: TripService) -> None:
    create = handler(
        _event(
            "POST",
            "/trips",
            body={
                "origin": "Chicago",
                "destination": "Japan",
                "destination_type": "country",
                "start_date": "2026-09-01",
                "end_date": "2026-09-07",
            },
        )
    )
    trip_id = json.loads(create["body"])["trip"]["trip_id"]
    propose = handler(_event("POST", f"/trips/{trip_id}/propose-cities"))
    route = json.loads(propose["body"])["route"]
    handler(
        _event(
            "PUT",
            f"/trips/{trip_id}/cities",
            body={
                "destination_type": route["destination_type"],
                "cities": route["cities"],
                "rationale": route.get("rationale") or "",
                "total_nights": route["total_nights"],
                "status": "confirmed",
            },
        )
    )
    plan = handler(_event("POST", f"/trips/{trip_id}/plan-next-day"))
    assert plan["statusCode"] == 200
    before = len(json.loads(plan["body"])["day"]["places"])

    suggested = handler(_event("POST", f"/trips/{trip_id}/days/1/suggest-place"))
    assert suggested["statusCode"] == 200
    body = json.loads(suggested["body"])
    assert body["place"]["place_key"]
    assert len(body["day"]["places"]) == before + 1
