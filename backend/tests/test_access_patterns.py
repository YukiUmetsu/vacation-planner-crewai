"""Access-pattern tests against the single-table schema (moto)."""

from __future__ import annotations

from typing import Any

from db import repository as repo


USER = "user-sub-1"
TRIP_A = "trip-aaa"
TRIP_B = "trip-bbb"


def _seed_trip(table: Any, trip_id: str, destination: str = "Japan") -> None:
    repo.put_trip(
        user_sub=USER,
        trip_id=trip_id,
        origin="Chicago",
        destination=destination,
        destination_type="country",
        start_date="2026-09-01",
        end_date="2026-09-07",
        day_count=7,
        preferences="food and museums",
        table=table,
    )


def test_list_trips_for_user(dynamodb_table: Any) -> None:
    _seed_trip(dynamodb_table, TRIP_A, "Japan")
    _seed_trip(dynamodb_table, TRIP_B, "Italy")

    trips = repo.list_trip_meta_for_user(user_sub=USER, table=dynamodb_table)
    assert len(trips) == 2
    destinations = {t["destination"] for t in trips}
    assert destinations == {"Japan", "Italy"}
    assert all(t["entity_type"] == "TRIP" for t in trips)


def test_get_trip_bundle_includes_route_and_days(dynamodb_table: Any) -> None:
    _seed_trip(dynamodb_table, TRIP_A)
    repo.put_route(
        user_sub=USER,
        trip_id=TRIP_A,
        route={
            "destination": "Japan",
            "destination_type": "country",
            "day_count": 7,
            "cities": [
                {"city": "Tokyo", "days": 4, "order": 1},
                {"city": "Kyoto", "days": 3, "order": 2},
            ],
            "rationale": "Classic first trip",
        },
        table=dynamodb_table,
    )
    repo.put_day(
        user_sub=USER,
        trip_id=TRIP_A,
        day={
            "day_index": 1,
            "date": "2026-09-01",
            "city": "Tokyo",
            "theme": "Arrival",
            "places": [],
            "notes": "Easy day",
        },
        table=dynamodb_table,
    )

    items = repo.get_trip_bundle(user_sub=USER, trip_id=TRIP_A, table=dynamodb_table)
    types = {i["entity_type"] for i in items}
    assert types == {"TRIP", "ROUTE", "DAY"}
    assert len(items) == 3


def test_gsi1_lookup_by_trip_id(dynamodb_table: Any) -> None:
    _seed_trip(dynamodb_table, TRIP_A)
    repo.put_route(
        user_sub=USER,
        trip_id=TRIP_A,
        route={"destination": "Japan", "cities": []},
        table=dynamodb_table,
    )

    items = repo.get_trip_by_id_via_gsi(trip_id=TRIP_A, table=dynamodb_table)
    assert len(items) >= 2
    assert all(i["gsi1pk"] == f"TRIP#{TRIP_A}" for i in items)
    meta = next(i for i in items if i["entity_type"] == "TRIP")
    assert meta["user_id"] == USER


def test_list_trips_excludes_route_and_day_rows(dynamodb_table: Any) -> None:
    _seed_trip(dynamodb_table, TRIP_A)
    repo.put_route(
        user_sub=USER,
        trip_id=TRIP_A,
        route={"destination": "Japan", "cities": []},
        table=dynamodb_table,
    )
    repo.put_day(
        user_sub=USER,
        trip_id=TRIP_A,
        day={
            "day_index": 1,
            "date": "2026-09-01",
            "city": "Tokyo",
            "theme": "x",
            "places": [],
            "notes": "",
        },
        table=dynamodb_table,
    )

    trips = repo.list_trip_meta_for_user(user_sub=USER, table=dynamodb_table)
    assert len(trips) == 1
    assert trips[0]["sk"] == f"TRIP#{TRIP_A}"
