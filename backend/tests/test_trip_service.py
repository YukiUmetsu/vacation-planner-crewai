"""Trip service flow with FakeCrewRunner + moto."""

from __future__ import annotations

from typing import Any

import pytest

from crews.fake_runner import FakeCrewRunner
from db import repository as repo
from http_utils import ApiError
from services.safety import NoopSafetyGate
from services.trip_service import TripService


USER = "test-user-1"


@pytest.fixture()
def service(dynamodb_table: Any) -> TripService:
    return TripService(
        table=dynamodb_table,
        runner=FakeCrewRunner(),
        safety=NoopSafetyGate(),
    )


def _create_country(service: TripService) -> str:
    result = service.create_trip(
        USER,
        {
            "origin": "Chicago",
            "destination": "Japan",
            "destination_type": "country",
            "start_date": "2026-09-01",
            "end_date": "2026-09-07",
            "preferences": "food and museums",
        },
    )
    assert result["trip"]["status"] == "drafting"
    assert result["route"] is None
    return result["trip"]["trip_id"]


def _confirm_country(service: TripService, trip_id: str) -> None:
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


def test_city_trip_auto_confirms_route(service: TripService) -> None:
    result = service.create_trip(
        USER,
        {
            "origin": "Chicago",
            "destination": "Tokyo",
            "destination_type": "city",
            "start_date": "2026-09-01",
            "end_date": "2026-09-03",
            "preferences": "",
        },
    )
    assert result["trip"]["status"] == "routing_confirmed"
    assert result["route"]["status"] == "confirmed"
    assert result["route"]["cities"][0]["city"] == "Tokyo"


def test_full_country_flow(service: TripService) -> None:
    trip_id = _create_country(service)

    proposed = service.propose_cities(USER, trip_id)
    assert proposed["trip"]["status"] == "awaiting_city_confirm"
    assert proposed["route"]["status"] == "proposed"
    assert len(proposed["route"]["cities"]) >= 1

    confirmed = service.confirm_cities(
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
    assert confirmed["trip"]["status"] == "routing_confirmed"
    assert confirmed["route"]["status"] == "confirmed"

    planned = service.plan_next_day(USER, trip_id)
    assert planned["day"]["day_index"] == 1
    assert planned["day"]["entity_type"] == "DAY"
    assert len(planned["day"]["places"]) >= 2
    assert planned["trip"]["next_day_index"] == 2
    assert planned["trip"]["status"] == "planning"
    assert planned["trip"]["visited_place_keys"]

    bundle = service.get_trip(USER, trip_id)
    assert bundle["trip"]["trip_id"] == trip_id
    assert bundle["route"] is not None
    assert len(bundle["days"]) == 1


def test_plan_before_confirm_rejected(service: TripService) -> None:
    trip_id = _create_country(service)
    with pytest.raises(ApiError) as exc:
        service.plan_next_day(USER, trip_id)
    assert exc.value.status_code == 409


def test_list_trips(service: TripService) -> None:
    _create_country(service)
    listed = service.list_trips(USER)
    assert len(listed["trips"]) == 1


def test_propose_cities_not_for_city(service: TripService) -> None:
    result = service.create_trip(
        USER,
        {
            "origin": "A",
            "destination": "Tokyo",
            "destination_type": "city",
            "start_date": "2026-09-01",
            "end_date": "2026-09-02",
        },
    )
    with pytest.raises(ApiError) as exc:
        service.propose_cities(USER, result["trip"]["trip_id"])
    assert exc.value.status_code == 409


def test_dedupe_empty_does_not_persist_duplicates(service: TripService) -> None:
    trip_id = _create_country(service)
    _confirm_country(service, trip_id)

    class AllDupesRunner(FakeCrewRunner):
        def plan_day(self, inputs: dict[str, Any]) -> dict[str, Any]:
            base = super().plan_day(inputs)
            places = [
                {
                    **place,
                    "name": f"Dup {i}",
                    "address": "same",
                    "place_key": "already|visited",
                }
                for i, place in enumerate(base["places"], start=1)
            ]
            return {**base, "places": places}

    service._runner = AllDupesRunner()
    repo.update_trip(
        user_sub=USER,
        trip_id=trip_id,
        updates={"visited_place_keys": ["already|visited"]},
        table=service._table,
    )

    with pytest.raises(ApiError) as exc:
        service.plan_next_day(USER, trip_id)
    assert exc.value.status_code == 422
    assert exc.value.code == "dedupe_empty"

    bundle = service.get_trip(USER, trip_id)
    assert bundle["days"] == []
    assert int(bundle["trip"]["next_day_index"]) == 1


def test_plan_next_day_conflict_when_day_already_written(
    service: TripService, dynamodb_table: Any
) -> None:
    trip_id = _create_country(service)
    _confirm_country(service, trip_id)
    first = service.plan_next_day(USER, trip_id)
    assert first["day"]["day_index"] == 1
    assert int(first["trip"]["next_day_index"]) == 2

    # Stale client: cursor rolled back but DAY#01 remains.
    repo.update_trip(
        user_sub=USER,
        trip_id=trip_id,
        updates={
            "next_day_index": 1,
            "status": "planning",
            "visited_place_keys": [],
            "prior_days_summary": "",
        },
        table=dynamodb_table,
    )

    with pytest.raises(ApiError) as exc:
        service.plan_next_day(USER, trip_id)
    assert exc.value.status_code == 409
    assert exc.value.code == "conflict"

    bundle = service.get_trip(USER, trip_id)
    assert len(bundle["days"]) == 1
    assert int(bundle["trip"]["next_day_index"]) == 1


def test_claim_next_day_rejects_stale_cursor(
    service: TripService, dynamodb_table: Any
) -> None:
    trip_id = _create_country(service)
    _confirm_country(service, trip_id)
    service.plan_next_day(USER, trip_id)

    with pytest.raises(repo.ConcurrentModificationError):
        repo.claim_next_day_slot(
            user_sub=USER,
            trip_id=trip_id,
            expected_next_day_index=1,
            new_status="planning",
            table=dynamodb_table,
        )


def test_confirm_rejects_route_with_day_gaps(service: TripService) -> None:
    trip_id = _create_country(service)
    service.propose_cities(USER, trip_id)
    with pytest.raises(ApiError) as exc:
        service.confirm_cities(
            USER,
            trip_id,
            {
                "destination_type": "country",
                "cities": [
                    {
                        "city": "Tokyo",
                        "country": "Japan",
                        "nights": 2,
                        "arrival_day_index": 1,
                        "departure_day_index": 3,
                        "reason": "gap after day 3",
                        "highlights": [],
                    }
                ],
                "rationale": "incomplete",
                "total_nights": 2,
                "status": "confirmed",
            },
        )
    assert exc.value.status_code == 400
    # 7-day trip expects 6 nights; incomplete coverage may surface as nights or gap.
    assert exc.value.code in {"route_gap", "route_nights_mismatch"}


def test_confirm_rejects_nights_not_matching_day_count(service: TripService) -> None:
    """1 night stretched across all days must not pass just because coverage is contiguous."""
    trip_id = _create_country(service)
    service.propose_cities(USER, trip_id)
    with pytest.raises(ApiError) as exc:
        service.confirm_cities(
            USER,
            trip_id,
            {
                "destination_type": "country",
                "cities": [
                    {
                        "city": "Tokyo",
                        "country": "Japan",
                        "nights": 1,
                        "arrival_day_index": 1,
                        "departure_day_index": 7,
                        "reason": "impossible nights vs window",
                        "highlights": [],
                    }
                ],
                "rationale": "bad nights",
                "total_nights": 1,
                "status": "confirmed",
            },
        )
    assert exc.value.status_code == 400
    assert exc.value.code == "route_nights_mismatch"


def test_confirm_rejects_overlapping_city_day_windows(service: TripService) -> None:
    """Contiguous union + correct nights must not hide duplicate day coverage."""
    trip_id = _create_country(service)
    service.propose_cities(USER, trip_id)
    with pytest.raises(ApiError) as exc:
        service.confirm_cities(
            USER,
            trip_id,
            {
                "destination_type": "country",
                "cities": [
                    {
                        "city": "Tokyo",
                        "country": "Japan",
                        "nights": 3,
                        "arrival_day_index": 1,
                        "departure_day_index": 4,
                        "reason": "overlaps Kyoto on day 4",
                        "highlights": [],
                    },
                    {
                        "city": "Kyoto",
                        "country": "Japan",
                        "nights": 3,
                        "arrival_day_index": 4,
                        "departure_day_index": 7,
                        "reason": "overlaps Tokyo on day 4",
                        "highlights": [],
                    },
                ],
                "rationale": "overlap",
                "total_nights": 6,
                "status": "confirmed",
            },
        )
    assert exc.value.status_code == 400
    assert exc.value.code == "route_overlap"
