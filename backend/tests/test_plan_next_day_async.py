"""Async plan-next-day claim + worker path (fake crew, injected enqueue)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from crews.fake_runner import FakeCrewRunner
from db import repository as repo
from http_utils import ApiError
from services.safety import NoopSafetyGate
from services.trip_service import TripService
from tests.test_trip_service import USER, _confirm_country, _create_country


@pytest.fixture()
def async_service(dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch) -> TripService:
    monkeypatch.setenv("PLAN_NEXT_DAY_ASYNC", "on")
    enqueued: list[tuple[str, str, int]] = []

    def _enqueue(user_sub: str, trip_id: str, day_index: int) -> None:
        enqueued.append((user_sub, trip_id, day_index))

    service = TripService(
        table=dynamodb_table,
        runner=FakeCrewRunner(),
        safety=NoopSafetyGate(),
        enqueue_plan_day=_enqueue,
    )
    service._enqueued = enqueued  # type: ignore[attr-defined]
    return service


def test_start_plan_next_day_claims_and_enqueues(async_service: TripService) -> None:
    trip_id = _create_country(async_service)
    _confirm_country(async_service, trip_id)

    started = async_service.start_plan_next_day(USER, trip_id)
    assert started["async"] is True
    assert started["planning_day_index"] == 1
    assert started["trip"]["planning_day_index"] == 1
    assert started["trip"]["next_day_index"] == 1
    assert async_service._enqueued == [(USER, trip_id, 1)]  # type: ignore[attr-defined]

    with pytest.raises(ApiError) as exc:
        async_service.start_plan_next_day(USER, trip_id)
    assert exc.value.code == "conflict"


def test_execute_plan_next_day_writes_day_and_clears_claim(
    async_service: TripService,
) -> None:
    trip_id = _create_country(async_service)
    _confirm_country(async_service, trip_id)
    async_service.start_plan_next_day(USER, trip_id)

    result = async_service.execute_plan_next_day(USER, trip_id, 1)
    assert result["day"]["day_index"] == 1
    assert result["trip"]["next_day_index"] == 2
    assert result["trip"].get("planning_day_index") is None
    assert not result["trip"].get("planning_error")

    bundle = async_service.get_trip(USER, trip_id)
    assert len(bundle["days"]) == 1


def test_stale_planning_claim_can_be_reclaimed(
    dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLAN_NEXT_DAY_ASYNC", "on")
    service = TripService(
        table=dynamodb_table,
        runner=FakeCrewRunner(),
        safety=NoopSafetyGate(),
        enqueue_plan_day=lambda *_a: None,
    )
    trip_id = _create_country(service)
    _confirm_country(service, trip_id)
    service.start_plan_next_day(USER, trip_id)

    stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    repo.update_trip(
        user_sub=USER,
        trip_id=trip_id,
        updates={"planning_started_at": stale},
        table=dynamodb_table,
    )

    # Second start should clear stale claim and succeed.
    started = service.start_plan_next_day(USER, trip_id)
    assert started["planning_day_index"] == 1


def test_execute_recovers_when_day_written_but_claim_not_cleared(
    async_service: TripService, dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DAY Put succeeded; complete_planning failed — retry must not re-crew."""
    trip_id = _create_country(async_service)
    _confirm_country(async_service, trip_id)
    async_service.start_plan_next_day(USER, trip_id)

    repo.put_day_if_absent(
        user_sub=USER,
        trip_id=trip_id,
        day={
            "day_index": 1,
            "date": "2026-08-01",
            "theme": "Orphan recovery",
            "overnight_city": "Tokyo",
            "places": [
                {
                    "name": "Senso-ji",
                    "place_key": "senso-ji",
                    "category": "other",
                    "estimated_minutes": 60,
                }
            ],
        },
        table=dynamodb_table,
    )

    trip = repo.get_trip_meta(user_sub=USER, trip_id=trip_id, table=dynamodb_table)
    assert trip is not None
    assert trip.get("planning_day_index") == 1
    assert int(trip.get("next_day_index") or 0) == 1

    calls = {"plan_day": 0}
    real_plan = async_service.runner.plan_day

    def _count_plan(inputs: dict[str, Any]) -> dict[str, Any]:
        calls["plan_day"] += 1
        return real_plan(inputs)

    monkeypatch.setattr(async_service.runner, "plan_day", _count_plan)

    result = async_service.execute_plan_next_day(USER, trip_id, 1)
    assert calls["plan_day"] == 0
    assert result["day"]["day_index"] == 1
    assert result["trip"]["next_day_index"] == 2
    assert result["trip"].get("planning_day_index") is None


def test_persist_retries_after_complete_planning_fails(
    async_service: TripService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If complete_planning fails after DAY write, claim stays and execute recovers."""
    trip_id = _create_country(async_service)
    _confirm_country(async_service, trip_id)
    async_service.start_plan_next_day(USER, trip_id)

    real_complete = repo.complete_planning_after_day_write
    calls = {"n": 0}

    def _fail_once(**kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated ddb failure after day write")
        return real_complete(**kwargs)

    monkeypatch.setattr(repo, "complete_planning_after_day_write", _fail_once)

    with pytest.raises(RuntimeError, match="simulated ddb"):
        async_service.execute_plan_next_day(USER, trip_id, 1)

    trip = async_service._require_trip(USER, trip_id)
    assert trip.get("planning_day_index") == 1
    assert int(trip.get("next_day_index") or 0) == 1
    assert repo.get_day(
        user_sub=USER, trip_id=trip_id, day_index=1, table=async_service._table
    )

    # Restore real complete via second execute (early finalize path).
    monkeypatch.setattr(repo, "complete_planning_after_day_write", real_complete)
    result = async_service.execute_plan_next_day(USER, trip_id, 1)
    assert result["trip"]["next_day_index"] == 2
    assert result["trip"].get("planning_day_index") is None


def test_start_recovers_stuck_day_without_enqueue(
    async_service: TripService, dynamodb_table: Any
) -> None:
    trip_id = _create_country(async_service)
    _confirm_country(async_service, trip_id)
    async_service.start_plan_next_day(USER, trip_id)
    async_service._enqueued.clear()  # type: ignore[attr-defined]

    repo.put_day_if_absent(
        user_sub=USER,
        trip_id=trip_id,
        day={
            "day_index": 1,
            "date": "2026-08-01",
            "theme": "Stuck",
            "overnight_city": "Tokyo",
            "places": [{"name": "A", "place_key": "a", "category": "other"}],
        },
        table=dynamodb_table,
    )

    result = async_service.start_plan_next_day(USER, trip_id)
    assert result["async"] is False
    assert result["day"]["day_index"] == 1
    assert result["trip"]["next_day_index"] == 2
    assert async_service._enqueued == []  # type: ignore[attr-defined]


def test_handler_worker_reraises_when_claim_held_after_day_write(
    async_service: TripService,
    dynamodb_table: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Event retries only run if the handler fails the invocation."""
    from handler import handler

    trip_id = _create_country(async_service)
    _confirm_country(async_service, trip_id)
    async_service.start_plan_next_day(USER, trip_id)

    monkeypatch.setattr("handler.TripService", lambda: async_service)

    real_complete = repo.complete_planning_after_day_write
    calls = {"n": 0}

    def _fail_once(**kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated ddb failure after day write")
        return real_complete(**kwargs)

    monkeypatch.setattr(repo, "complete_planning_after_day_write", _fail_once)

    worker_event = {
        "worker": "plan_next_day",
        "user_sub": USER,
        "trip_id": trip_id,
        "day_index": 1,
    }
    with pytest.raises(RuntimeError, match="simulated ddb"):
        handler(worker_event)

    trip = repo.get_trip_meta(user_sub=USER, trip_id=trip_id, table=dynamodb_table)
    assert trip is not None
    assert trip.get("planning_day_index") == 1
    assert repo.get_day(
        user_sub=USER, trip_id=trip_id, day_index=1, table=dynamodb_table
    )

    # Lambda Event retry (second invoke) recovers via finalize.
    monkeypatch.setattr(repo, "complete_planning_after_day_write", real_complete)
    assert handler(worker_event) == {"ok": True}
    trip = repo.get_trip_meta(user_sub=USER, trip_id=trip_id, table=dynamodb_table)
    assert trip is not None
    assert trip.get("planning_day_index") is None
    assert int(trip.get("next_day_index") or 0) == 2


def test_handler_worker_swallows_when_claim_already_cleared(
    async_service: TripService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Terminal fail_planning cleared the claim — do not fail the invoke for retries."""
    from handler import handler

    trip_id = _create_country(async_service)
    _confirm_country(async_service, trip_id)
    async_service.start_plan_next_day(USER, trip_id)

    monkeypatch.setattr("handler.TripService", lambda: async_service)

    def _boom(*_a: Any, **_k: Any) -> dict[str, Any]:
        repo.fail_planning_in_progress(
            user_sub=USER,
            trip_id=trip_id,
            planned_day_index=1,
            error_message="crew_failed",
            table=async_service._table,
        )
        raise RuntimeError("crew_failed")

    monkeypatch.setattr(async_service, "execute_plan_next_day", _boom)

    result = handler(
        {
            "worker": "plan_next_day",
            "user_sub": USER,
            "trip_id": trip_id,
            "day_index": 1,
        }
    )
    assert result == {"ok": False, "terminal": True}


def test_execute_preserves_claim_on_retryable_agent_error(
    async_service: TripService,
    dynamodb_table: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trip_id = _create_country(async_service)
    _confirm_country(async_service, trip_id)
    async_service.start_plan_next_day(USER, trip_id)

    def _boom(_inputs: dict[str, Any]) -> dict[str, Any]:
        raise ApiError(
            502,
            "AgentCore invoke failed: TimeoutError",
            code="agent_invoke_failed",
            retryable=True,
        )

    monkeypatch.setattr(async_service.runner, "plan_day", _boom)

    with pytest.raises(ApiError) as exc:
        async_service.execute_plan_next_day(USER, trip_id, 1)
    assert exc.value.retryable is True

    trip = repo.get_trip_meta(user_sub=USER, trip_id=trip_id, table=dynamodb_table)
    assert trip is not None
    assert trip.get("planning_day_index") == 1
    assert trip.get("status") == "planning"
    assert not trip.get("planning_error")


def test_handler_worker_reraises_retryable_agent_error(
    async_service: TripService,
    dynamodb_table: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from handler import handler

    trip_id = _create_country(async_service)
    _confirm_country(async_service, trip_id)
    async_service.start_plan_next_day(USER, trip_id)
    monkeypatch.setattr("handler.TripService", lambda: async_service)

    def _boom(_inputs: dict[str, Any]) -> dict[str, Any]:
        raise ApiError(
            502,
            "AgentCore invoke failed: ThrottlingException",
            code="agent_invoke_failed",
            retryable=True,
        )

    monkeypatch.setattr(async_service.runner, "plan_day", _boom)

    with pytest.raises(ApiError) as exc:
        handler(
            {
                "worker": "plan_next_day",
                "user_sub": USER,
                "trip_id": trip_id,
                "day_index": 1,
            }
        )
    assert exc.value.retryable is True
    trip = repo.get_trip_meta(user_sub=USER, trip_id=trip_id, table=dynamodb_table)
    assert trip is not None
    assert trip.get("planning_day_index") == 1
