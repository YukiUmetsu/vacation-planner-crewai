"""Async propose / suggest-* claim + 202 path (fake crew, injected enqueue)."""

from __future__ import annotations

from typing import Any

import pytest

from crews.fake_runner import FakeCrewRunner
from db import repository as repo
from safety.gate import NoopSafetyGate
from trips.service import TripService
from tests.test_trip_service import USER, _confirm_country, _create_country


@pytest.fixture()
def async_crew_service(dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch) -> TripService:
    monkeypatch.setenv("CREW_LLM_ASYNC", "on")
    enqueued: list[dict[str, Any]] = []

    def _enqueue(payload: dict[str, Any]) -> None:
        enqueued.append(payload)

    service = TripService(
        table=dynamodb_table,
        runner=FakeCrewRunner(),
        safety=NoopSafetyGate(),
        enqueue_crew_job=_enqueue,
    )
    service._enqueued = enqueued  # type: ignore[attr-defined]
    return service


def test_propose_cities_claims_and_enqueues(async_crew_service: TripService) -> None:
    trip_id = _create_country(async_crew_service)
    started = async_crew_service.propose_cities(USER, trip_id)
    assert started["async"] is True
    assert started["job"] == "propose_cities"
    assert started["trip"]["crew_job_kind"] == "propose_cities"
    assert async_crew_service._enqueued[0]["worker"] == "propose_cities"  # type: ignore[attr-defined]

    result = async_crew_service.execute_propose_cities(USER, trip_id)
    assert result["route"]["status"] == "proposed"
    assert result["trip"].get("crew_job_kind") is None
    assert result["trip"]["status"] == "awaiting_city_confirm"


def test_suggest_city_persists_candidates_for_poll(
    async_crew_service: TripService,
) -> None:
    trip_id = _create_country(async_crew_service)
    started = async_crew_service.suggest_city(
        USER, trip_id, {"hint": "coast", "count": 1}
    )
    assert started["async"] is True
    assert started["job"] == "suggest_city"

    result = async_crew_service.execute_suggest_city(USER, trip_id)
    assert result["candidates"]
    assert result["trip"].get("crew_job_kind") is None
    assert result["trip"].get("suggest_city_candidates")


def test_suggest_place_async_after_day_planned(
    async_crew_service: TripService, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Plan day stays sync unless PLAN_NEXT_DAY_ASYNC / agentcore — force sync plan.
    monkeypatch.setenv("CREW_LLM_ASYNC", "off")
    trip_id = _create_country(async_crew_service)
    _confirm_country(async_crew_service, trip_id)
    planned = async_crew_service.plan_next_day(USER, trip_id)
    assert planned.get("async") is not True
    day_index = int(planned["day"]["day_index"])

    monkeypatch.setenv("CREW_LLM_ASYNC", "on")
    started = async_crew_service.suggest_place(USER, trip_id, day_index)
    assert started["async"] is True
    assert started["day_index"] == day_index
    assert started["baseline_place_count"] >= 1

    result = async_crew_service.execute_suggest_place(USER, trip_id, day_index)
    assert result["place"]["place_key"]
    assert len(result["day"]["places"]) > started["baseline_place_count"]
    assert result["trip"].get("crew_job_kind") is None


def test_execute_propose_keeps_claim_on_retryable_error(
    async_crew_service: TripService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from http_utils import ApiError

    trip_id = _create_country(async_crew_service)
    async_crew_service.propose_cities(USER, trip_id)

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise ApiError(502, "transient", code="agent_invoke_failed", retryable=True)

    monkeypatch.setattr(
        "trips.city_route._propose_cities_sync",
        _boom,
    )
    with pytest.raises(ApiError) as exc:
        async_crew_service.execute_propose_cities(USER, trip_id)
    assert exc.value.retryable is True
    trip = repo.get_trip_meta(
        user_sub=USER, trip_id=trip_id, table=async_crew_service._table
    )
    assert trip is not None
    assert trip.get("crew_job_kind") == "propose_cities"
    assert not trip.get("crew_job_error")


def test_execute_suggest_place_recovers_after_partial_persist(
    async_crew_service: TripService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Persist succeeded but claim still held → retry must not append again."""
    monkeypatch.setenv("CREW_LLM_ASYNC", "off")
    trip_id = _create_country(async_crew_service)
    _confirm_country(async_crew_service, trip_id)
    planned = async_crew_service.plan_next_day(USER, trip_id)
    day_index = int(planned["day"]["day_index"])
    baseline = len(planned["day"]["places"])

    monkeypatch.setenv("CREW_LLM_ASYNC", "on")
    started = async_crew_service.suggest_place(USER, trip_id, day_index)
    assert started["baseline_place_count"] == baseline

    # First execute writes the place.
    first = async_crew_service.execute_suggest_place(USER, trip_id, day_index)
    assert len(first["day"]["places"]) == baseline + 1
    place_key = first["place"]["place_key"]

    # Simulate Lambda death after persist: re-claim with same baseline.
    repo.claim_crew_job(
        user_sub=USER,
        trip_id=trip_id,
        kind=repo.JOB_SUGGEST_PLACE,
        day_index=day_index,
        baseline_place_count=baseline,
        request={},
        table=async_crew_service._table,
    )
    second = async_crew_service.execute_suggest_place(USER, trip_id, day_index)
    assert second["place"]["place_key"] == place_key
    assert len(second["day"]["places"]) == baseline + 1
    assert second["trip"].get("crew_job_kind") is None


def test_handler_propose_returns_202(
    dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from handler import handler

    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("CREW_LLM_ASYNC", "on")
    enqueued: list[dict[str, Any]] = []

    service = TripService(
        table=dynamodb_table,
        runner=FakeCrewRunner(),
        safety=NoopSafetyGate(),
        enqueue_crew_job=lambda p: enqueued.append(p),
    )

    def _svc(**_kwargs: Any) -> TripService:
        return service

    monkeypatch.setattr("routes.trips._service", _svc)

    trip_id = _create_country(service)
    resp = handler(
        {
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": f"/trips/{trip_id}/propose-cities",
            "headers": {"x-dev-user-sub": USER},
            "body": "{}",
        }
    )
    assert resp["statusCode"] == 202
    body = json.loads(resp["body"])
    assert body["job"] == "propose_cities"
    assert body["trip"]["crew_job_kind"] == "propose_cities"
    assert enqueued
