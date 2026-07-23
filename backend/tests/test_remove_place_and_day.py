"""Remove place and delete day plan APIs."""

from __future__ import annotations

import json
from typing import Any

import pytest

from crews.fake_runner import FakeCrewRunner
from db import repository as repo
from handler import handler
from routes import trips as trip_routes
from services.safety import NoopSafetyGate
from services.trip_service import TripService


USER = "test-user-remove"


@pytest.fixture()
def service(dynamodb_table: Any) -> TripService:
    return TripService(
        table=dynamodb_table,
        runner=FakeCrewRunner(),
        safety=NoopSafetyGate(),
    )


@pytest.fixture()
def wired(dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch) -> TripService:
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


def _event(method: str, path: str, body: dict | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {
        "requestContext": {"http": {"method": method}},
        "rawPath": path,
        "headers": {"x-dev-user-sub": USER},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _plan_one_day(service: TripService) -> str:
    created = service.create_trip(
        USER,
        {
            "origin": "Chicago",
            "destination": "Japan",
            "destination_type": "country",
            "start_date": "2026-09-01",
            "end_date": "2026-09-07",
            "preferences": "food",
        },
    )
    trip_id = created["trip"]["trip_id"]
    proposed = service.propose_cities(USER, trip_id)
    service.confirm_cities(
        USER,
        trip_id,
        {
            "destination_type": "country",
            "cities": proposed["route"]["cities"],
            "rationale": proposed["route"]["rationale"],
            "total_nights": proposed["route"]["total_nights"],
            "status": "confirmed",
        },
    )
    service.plan_next_day(USER, trip_id)
    return trip_id


def test_remove_place_reindexes_and_updates_visited(service: TripService) -> None:
    trip_id = _plan_one_day(service)
    day = repo.get_day(user_sub=USER, trip_id=trip_id, day_index=1, table=service._table)
    assert day is not None
    before = list(day["places"])
    assert len(before) >= 2
    removed_key = str(before[1].get("place_key") or "")

    result = service.remove_place(USER, trip_id, 1, 1)
    places = result["day"]["places"]
    assert len(places) == len(before) - 1
    assert [p["order_in_day"] for p in places] == list(range(1, len(places) + 1))
    if removed_key:
        assert removed_key not in (result["trip"].get("visited_place_keys") or [])


def test_delete_day_rewinds_cursor(service: TripService) -> None:
    trip_id = _plan_one_day(service)
    service.plan_next_day(USER, trip_id)
    bundle = service.get_trip(USER, trip_id)
    assert len(bundle["days"]) >= 2

    result = service.delete_day(USER, trip_id, 1)
    assert result["deleted_day_index"] == 1
    assert all(int(d["day_index"]) != 1 for d in result["days"])
    assert result["trip"]["next_day_index"] == 1
    assert result["trip"]["status"] == "planning"
    assert repo.get_day(user_sub=USER, trip_id=trip_id, day_index=1, table=service._table) is None


def test_delete_last_day_returns_to_routing_confirmed(service: TripService) -> None:
    trip_id = _plan_one_day(service)
    result = service.delete_day(USER, trip_id, 1)
    assert result["days"] == []
    assert result["trip"]["next_day_index"] == 1
    assert result["trip"]["status"] == "routing_confirmed"


def test_delete_day_rejects_while_planning_in_progress(
    service: TripService, dynamodb_table: Any
) -> None:
    trip_id = _plan_one_day(service)
    repo.update_trip(
        user_sub=USER,
        trip_id=trip_id,
        updates={"planning_day_index": 2, "planning_started_at": "2099-01-01T00:00:00+00:00"},
        table=dynamodb_table,
    )

    from http_utils import ApiError

    with pytest.raises(ApiError) as exc:
        service.delete_day(USER, trip_id, 1)
    assert exc.value.status_code == 409
    assert exc.value.code == "planning_in_progress"
    assert repo.get_day(user_sub=USER, trip_id=trip_id, day_index=1, table=dynamodb_table)


def test_delete_trip_rejects_while_planning_in_progress(
    service: TripService, dynamodb_table: Any
) -> None:
    trip_id = _plan_one_day(service)
    repo.update_trip(
        user_sub=USER,
        trip_id=trip_id,
        updates={"planning_day_index": 2, "planning_started_at": "2099-01-01T00:00:00+00:00"},
        table=dynamodb_table,
    )

    from http_utils import ApiError

    with pytest.raises(ApiError) as exc:
        service.delete_trip(USER, trip_id)
    assert exc.value.status_code == 409
    assert exc.value.code == "planning_in_progress"
    assert repo.get_trip_meta(user_sub=USER, trip_id=trip_id, table=dynamodb_table)


def test_remove_place_rejects_while_planning_in_progress(
    service: TripService, dynamodb_table: Any
) -> None:
    trip_id = _plan_one_day(service)
    repo.update_trip(
        user_sub=USER,
        trip_id=trip_id,
        updates={"planning_day_index": 2, "planning_started_at": "2099-01-01T00:00:00+00:00"},
        table=dynamodb_table,
    )

    from http_utils import ApiError

    with pytest.raises(ApiError) as exc:
        service.remove_place(USER, trip_id, 1, 0)
    assert exc.value.status_code == 409
    assert exc.value.code == "planning_in_progress"


def test_apply_itinerary_edit_rejects_deleting_status(
    service: TripService, dynamodb_table: Any
) -> None:
    trip_id = _plan_one_day(service)
    repo.begin_trip_delete(user_sub=USER, trip_id=trip_id, table=dynamodb_table)

    with pytest.raises(repo.ConcurrentModificationError):
        repo.apply_itinerary_edit(
            user_sub=USER,
            trip_id=trip_id,
            next_day_index=1,
            status="planning",
            prior_days_summary="",
            table=dynamodb_table,
        )

    trip = repo.get_trip_meta(user_sub=USER, trip_id=trip_id, table=dynamodb_table)
    assert trip is not None
    assert trip.get("status") == "deleting"


def test_remove_place_and_delete_day_routes(wired: TripService) -> None:
    trip_id = _plan_one_day(wired)
    day = repo.get_day(user_sub=USER, trip_id=trip_id, day_index=1, table=wired._table)
    assert day is not None
    before = len(day["places"])

    removed = handler(_event("DELETE", f"/trips/{trip_id}/days/1/places/0"))
    assert removed["statusCode"] == 200
    body = json.loads(removed["body"])
    assert len(body["day"]["places"]) == before - 1

    deleted = handler(_event("DELETE", f"/trips/{trip_id}/days/1"))
    assert deleted["statusCode"] == 200
    body = json.loads(deleted["body"])
    assert body["deleted_day_index"] == 1
    assert body["days"] == []
