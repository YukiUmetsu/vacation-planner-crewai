"""Reorder place within a day."""

from __future__ import annotations

from typing import Any

import pytest

from http_utils import ApiError
from trips.day_edit import reorder_place


def test_reorder_place_moves_and_reindexes(monkeypatch: pytest.MonkeyPatch) -> None:
    from db import repository as repo

    day = {
        "pk": "USER#u1",
        "sk": "TRIP#t1#DAY#1",
        "entity_type": "DAY",
        "trip_id": "t1",
        "day_index": 1,
        "places": [
            {"name": "A", "place_key": "a", "order_in_day": 1},
            {"name": "B", "place_key": "b", "order_in_day": 2},
            {"name": "C", "place_key": "c", "order_in_day": 3},
        ],
    }
    trip = {
        "pk": "USER#u1",
        "sk": "TRIP#t1",
        "entity_type": "TRIP",
        "trip_id": "t1",
        "user_id": "u1",
        "status": "planning_days",
        "day_count": 3,
    }

    def _bundle(**_k: Any) -> list[dict[str, Any]]:
        return [trip, day]

    captured: dict[str, Any] = {}

    def _replace(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {**day, "places": kwargs["places"]}

    monkeypatch.setattr(
        "trips.day_edit._load_owned_bundle",
        lambda **_k: (trip, None, [day]),
    )
    monkeypatch.setattr(repo, "replace_day_places", _replace)

    out = reorder_place(
        user_sub="u1",
        trip_id="t1",
        day_index=1,
        from_index=0,
        to_index=2,
        table=None,
    )
    names = [p["name"] for p in captured["places"]]
    orders = [p["order_in_day"] for p in captured["places"]]
    assert names == ["B", "C", "A"]
    assert orders == [1, 2, 3]
    assert out["day"]["places"][0]["name"] == "B"


def test_reorder_place_rejects_bad_index(monkeypatch: pytest.MonkeyPatch) -> None:
    trip = {
        "trip_id": "t1",
        "user_id": "u1",
        "status": "planning_days",
    }
    day = {"day_index": 1, "places": [{"name": "A", "place_key": "a"}]}
    monkeypatch.setattr(
        "trips.day_edit._load_owned_bundle",
        lambda **_k: (trip, None, [day]),
    )
    with pytest.raises(ApiError) as exc:
        reorder_place(
            user_sub="u1",
            trip_id="t1",
            day_index=1,
            from_index=0,
            to_index=5,
            table=None,
        )
    assert exc.value.code == "not_found"
