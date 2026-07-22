"""Tests for Google Places open-status enrichment (soft BFF gate)."""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest

from http_utils import ApiError
from services.place_quality import filter_quality_places, validate_suggested_place
from services.places_client import PlacesLookupResult
from services.places_enrich import (
    apply_lookup_to_place,
    closed_weekdays_from_hours,
    enrich_place,
    enrich_places,
    google_day_to_python_weekday,
    is_always_open_hours,
    location_compatible,
    map_business_status,
    names_match,
    pick_matching_lookup,
)


def test_google_day_to_python_weekday() -> None:
    assert google_day_to_python_weekday(0) == 6
    assert google_day_to_python_weekday(1) == 0
    assert google_day_to_python_weekday(6) == 5


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("OPERATIONAL", "open"),
        ("CLOSED_PERMANENTLY", "closed"),
        ("CLOSED_TEMPORARILY", "closed"),
        ("FUTURE_OPENING", "closed"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_map_business_status(status: str | None, expected: str) -> None:
    assert map_business_status(status) == expected


def test_closed_weekdays_from_hours_weekdays_only() -> None:
    hours = {
        "periods": [
            {"open": {"day": d, "hour": 9, "minute": 0}} for d in range(1, 6)
        ],
    }
    assert closed_weekdays_from_hours(hours) == [5, 6]


def test_always_open_hours_empty_closed_weekdays() -> None:
    hours = {"periods": [{"open": {"day": 0, "hour": 0, "minute": 0}}]}
    assert is_always_open_hours(hours) is True
    assert closed_weekdays_from_hours(hours) == []
    # null close still counts as always-open
    hours_null_close = {
        "periods": [{"open": {"day": 0, "hour": 0, "minute": 0}, "close": None}]
    }
    assert is_always_open_hours(hours_null_close) is True


def test_names_match_and_pick() -> None:
    assert names_match("Senso-ji Temple", "Senso-ji")
    assert names_match("Tokyo Tower", "Tokyo Tower")
    assert not names_match("Senso-ji", "Tokyo Skytree")
    assert not names_match("Park", "Parking Garage")

    wrong = PlacesLookupResult(
        "1", "OPERATIONAL", "1 Skytree, Tokyo", "Tokyo Skytree", None
    )
    right = PlacesLookupResult(
        "2", "CLOSED_PERMANENTLY", "2 Asakusa, Tokyo", "Senso-ji Temple", None
    )
    picked = pick_matching_lookup(
        "Senso-ji",
        [wrong, right],
        overnight_city="Tokyo",
    )
    assert picked is right
    assert (
        pick_matching_lookup("Senso-ji", [wrong], overnight_city="Tokyo") is None
    )


def test_location_compatible_requires_city_or_address() -> None:
    assert location_compatible(
        crew_address="",
        overnight_city="Tokyo",
        formatted_address="1-1 Asakusa, Taito City, Tokyo 111-0032, Japan",
    )
    assert not location_compatible(
        crew_address="",
        overnight_city="Tokyo",
        formatted_address="1-1 Umeda, Osaka 530-0001, Japan",
    )
    assert not location_compatible(
        crew_address="",
        overnight_city="Tokyo",
        formatted_address=None,
    )
    assert location_compatible(
        crew_address="1-2 Dogenzaka, Shibuya, Tokyo",
        overnight_city="Tokyo",
        formatted_address="1-2 Dogenzaka, Shibuya City, Tokyo, Japan",
    )
    # Address given but hit is a different branch in another city — reject.
    assert not location_compatible(
        crew_address="1-2 Dogenzaka, Shibuya, Tokyo",
        overnight_city="Tokyo",
        formatted_address="2-1 Umeda, Osaka, Japan",
    )


def test_pick_skips_same_name_wrong_city_before_correct() -> None:
    """Closed wrong-city branch must not win over the open local branch."""
    wrong = PlacesLookupResult(
        place_id="osaka",
        business_status="CLOSED_PERMANENTLY",
        formatted_address="1-1 Umeda, Osaka, Japan",
        display_name="Starbucks",
        regular_opening_hours=None,
    )
    right = PlacesLookupResult(
        place_id="tokyo",
        business_status="OPERATIONAL",
        formatted_address="1-2 Dogenzaka, Shibuya, Tokyo, Japan",
        display_name="Starbucks",
        regular_opening_hours=None,
    )
    picked = pick_matching_lookup(
        "Starbucks",
        [wrong, right],
        crew_address="1-2 Dogenzaka, Shibuya, Tokyo",
        overnight_city="Tokyo",
    )
    assert picked is right
    assert picked.business_status == "OPERATIONAL"


def test_enrich_rejects_same_name_wrong_city_hit() -> None:
    client = MagicMock()
    client.search_text.return_value = [
        PlacesLookupResult(
            place_id="osaka",
            business_status="CLOSED_PERMANENTLY",
            formatted_address="1-1 Umeda, Osaka, Japan",
            display_name="Starbucks",
            regular_opening_hours=None,
        )
    ]
    place = {
        "name": "Starbucks",
        "address": "1-2 Dogenzaka, Shibuya, Tokyo",
        "operational_status": "open",
    }
    out = enrich_place(place, overnight_city="Tokyo", client=client)
    assert out is place
    assert out["operational_status"] == "open"


def test_apply_lookup_sets_status_and_place_id() -> None:
    place = {"name": "Cafe", "operational_status": "unknown"}
    lookup = PlacesLookupResult(
        place_id="ChIJabc",
        business_status="CLOSED_PERMANENTLY",
        formatted_address="1 Main St",
        display_name="Cafe",
        regular_opening_hours=None,
    )
    out = apply_lookup_to_place(place, lookup)
    assert out["operational_status"] == "closed"
    assert out["place_id"] == "ChIJabc"
    assert out["address"] == "1 Main St"
    assert place["operational_status"] == "unknown"


def test_enrich_no_key_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    monkeypatch.setenv("PLACES_ENRICH", "on")
    place = {"name": "Senso-ji", "operational_status": "unknown"}
    assert enrich_place(place, overnight_city="Tokyo") is place
    assert enrich_places([place], overnight_city="Tokyo") == [place]


def test_enrich_off_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "fake-key")
    monkeypatch.setenv("PLACES_ENRICH", "off")
    place = {"name": "Senso-ji", "operational_status": "unknown"}
    assert enrich_place(place, overnight_city="Tokyo") is place


def test_enrich_skips_already_closed_without_http() -> None:
    client = MagicMock()
    place = {"name": "Dead Cafe", "operational_status": "closed"}
    out = enrich_place(place, overnight_city="Tokyo", client=client)
    assert out is place
    client.search_text.assert_not_called()


def test_enrich_soft_fails_when_client_returns_empty() -> None:
    client = MagicMock()
    client.search_text.return_value = []
    place = {"name": "Mystery Spot", "operational_status": "open"}
    out = enrich_place(place, overnight_city="Tokyo", client=client)
    assert out is place
    client.search_text.assert_called_once()


def test_enrich_rejects_wrong_name_hit() -> None:
    client = MagicMock()
    client.search_text.return_value = [
        PlacesLookupResult(
            place_id="x",
            business_status="CLOSED_PERMANENTLY",
            formatted_address=None,
            display_name="Completely Different Spot",
            regular_opening_hours=None,
        )
    ]
    place = {"name": "Senso-ji", "operational_status": "unknown"}
    out = enrich_place(place, overnight_city="Tokyo", client=client)
    assert out is place
    assert out["operational_status"] == "unknown"


def test_enrich_soft_fails_when_client_raises() -> None:
    client = MagicMock()
    client.search_text.side_effect = RuntimeError("boom")
    place = {"name": "Mystery Spot", "operational_status": "open"}
    out = enrich_place(place, overnight_city="Tokyo", client=client)
    assert out is place


def test_enrich_then_filter_drops_permanently_closed() -> None:
    def _open_hit(name: str, pid: str) -> PlacesLookupResult:
        return PlacesLookupResult(
            place_id=pid,
            business_status="OPERATIONAL",
            formatted_address=f"{name}, Tokyo, Japan",
            display_name=name,
            regular_opening_hours={
                "periods": [
                    {"open": {"day": d, "hour": 9, "minute": 0}} for d in range(7)
                ],
            },
        )

    responses = {
        "Closed Cafe": [
            PlacesLookupResult(
                place_id="1",
                business_status="CLOSED_PERMANENTLY",
                formatted_address="Closed Cafe, Tokyo, Japan",
                display_name="Closed Cafe",
                regular_opening_hours=None,
            )
        ],
        "Park A": [_open_hit("Park A", "2")],
        "Park B": [_open_hit("Park B", "3")],
        "Park C": [_open_hit("Park C", "4")],
    }

    def _search(query: str, **_kwargs: object) -> list[PlacesLookupResult]:
        for name, hits in responses.items():
            if name in query:
                return hits
        return []

    client = MagicMock()
    client.search_text.side_effect = _search

    places = [
        {"name": "Closed Cafe", "estimated_minutes": 60, "operational_status": "unknown"},
        {"name": "Park A", "estimated_minutes": 60, "operational_status": "unknown"},
        {"name": "Park B", "estimated_minutes": 60, "operational_status": "unknown"},
        {"name": "Park C", "estimated_minutes": 60, "operational_status": "unknown"},
    ]
    enriched = enrich_places(places, overnight_city="Tokyo", client=client)
    kept = filter_quality_places(
        enriched,
        plan_date=date(2026, 9, 1),
        max_comfortable_minutes=510,
    )
    assert "Closed Cafe" not in {p["name"] for p in kept}
    assert len(kept) >= 3


def test_enrich_weekday_closed_from_hours() -> None:
    hours = {
        "periods": [
            {"open": {"day": d, "hour": 10, "minute": 0}} for d in [0, 2, 3, 4, 5, 6]
        ],
    }
    client = MagicMock()
    client.search_text.return_value = [
        PlacesLookupResult(
            place_id="m1",
            business_status="OPERATIONAL",
            formatted_address="Monday Museum, Tokyo, Japan",
            display_name="Monday Museum",
            regular_opening_hours=hours,
        )
    ]
    place = {
        "name": "Monday Museum",
        "estimated_minutes": 90,
        "operational_status": "unknown",
        "closed_weekdays": [],
    }
    enriched = enrich_place(place, overnight_city="Tokyo", client=client)
    assert enriched["operational_status"] == "open"
    assert 0 in enriched["closed_weekdays"]

    with pytest.raises(ApiError) as exc_info:
        validate_suggested_place(
            enriched,
            existing_places=[
                {"name": "A", "estimated_minutes": 60, "place_key": "a"},
                {"name": "B", "estimated_minutes": 60, "place_key": "b"},
            ],
            plan_date=date(2026, 8, 31),
            max_comfortable_minutes=510,
        )
    assert exc_info.value.code == "place_weekday_closed"


def test_enrich_always_open_not_weekday_closed() -> None:
    hours = {"periods": [{"open": {"day": 0, "hour": 0, "minute": 0}}]}
    client = MagicMock()
    client.search_text.return_value = [
        PlacesLookupResult(
            place_id="24",
            business_status="OPERATIONAL",
            formatted_address="Konbini 24, Tokyo, Japan",
            display_name="Konbini 24",
            regular_opening_hours=hours,
        )
    ]
    place = {"name": "Konbini 24", "estimated_minutes": 20, "operational_status": "unknown"}
    enriched = enrich_place(place, overnight_city="Tokyo", client=client)
    assert enriched["closed_weekdays"] == []
    assert enriched["open_hours"] == "Open 24 hours"
    ok = validate_suggested_place(
        enriched,
        existing_places=[
            {"name": "A", "estimated_minutes": 60, "place_key": "a"},
            {"name": "B", "estimated_minutes": 60, "place_key": "b"},
        ],
        plan_date=date(2026, 8, 31),
        max_comfortable_minutes=510,
    )
    assert ok["name"] == "Konbini 24"


def test_google_client_parses_results(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.places_client import GooglePlacesClient

    captured: dict[str, Any] = {}

    class _Resp:
        def __enter__(self) -> Any:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return (
                b'{"places":[{"id":"places/ChIJ1","businessStatus":"OPERATIONAL",'
                b'"displayName":{"text":"Cafe"},"formattedAddress":"1 St",'
                b'"regularOpeningHours":{"periods":[{"open":{"day":1,"hour":9,"minute":0}}]}}]}'
            )

    def _urlopen(req: Any, *a: object, **k: object) -> Any:
        captured["body"] = req.data
        return _Resp()

    monkeypatch.setattr(
        "services.places_client.urllib.request.urlopen",
        _urlopen,
    )
    client = GooglePlacesClient("test-key")
    results = client.search_text("Cafe, Tokyo")
    assert len(results) == 1
    assert results[0].place_id == "ChIJ1"
    assert results[0].business_status == "OPERATIONAL"
    assert results[0].display_name == "Cafe"
    body = __import__("json").loads(captured["body"].decode("utf-8"))
    assert body["pageSize"] == 5
    assert "maxResultCount" not in body


def test_google_client_soft_fails_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.places_client import GooglePlacesClient
    import urllib.error

    def _raise(*_a: object, **_k: object) -> None:
        raise urllib.error.URLError("network down")

    monkeypatch.setattr("services.places_client.urllib.request.urlopen", _raise)
    assert GooglePlacesClient("test-key").search_text("Cafe") == []
