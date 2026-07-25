"""Tests for Wikidata P18 and Openverse image fallbacks."""

from __future__ import annotations

from typing import Any

import pytest

from places import openverse_fallback as openverse
from places import wikidata_fallback as wikidata


def test_wikidata_backoff_skips_network(monkeypatch: pytest.MonkeyPatch) -> None:
    wikidata.clear_wikidata_backoff_for_tests()
    calls = {"n": 0}

    def _json(*_a: Any, **_k: Any) -> dict[str, Any] | None:
        calls["n"] += 1
        return None

    monkeypatch.setattr(wikidata, "http_get_json", _json)
    wikidata.note_wikidata_transient(seconds=60)
    with pytest.raises(wikidata.PlacesTransientError):
        wikidata.lookup_wikidata_image_url("Nijo Castle", city="Kyoto")
    assert calls["n"] == 0
    wikidata.clear_wikidata_backoff_for_tests()


def test_resolve_wikidata_photo_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    wikidata.clear_wikidata_backoff_for_tests()

    def _json(url: str, **_k: Any) -> dict[str, Any] | None:
        if "wbsearchentities" in url:
            return {
                "search": [
                    {
                        "id": "Q1013399",
                        "label": "Nijō Castle",
                        "description": "castle in Kyoto, Japan",
                    }
                ]
            }
        if "wbgetentities" in url:
            return {
                "entities": {
                    "Q1013399": {
                        "claims": {
                            "P18": [
                                {
                                    "mainsnak": {
                                        "datavalue": {
                                            "value": "Nijo Castle.jpg",
                                            "type": "string",
                                        }
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        return None

    monkeypatch.setattr(wikidata, "http_get_json", _json)
    monkeypatch.setattr(
        wikidata,
        "payload_from_image_url",
        lambda url, **_k: {
            "photo_url": url,
            "places_photo_name": None,
            "photo_data_url": "data:image/jpeg;base64,abc",
        },
    )
    payload = wikidata.resolve_wikidata_photo_payload("Nijo Castle", city="Kyoto")
    assert payload["photo_data_url"] == "data:image/jpeg;base64,abc"
    assert payload["photo_url"]
    assert "Special:FilePath" in (payload["photo_url"] or "")


def test_openverse_backoff_skips_network(monkeypatch: pytest.MonkeyPatch) -> None:
    openverse.clear_openverse_backoff_for_tests()
    calls = {"n": 0}

    def _json(*_a: Any, **_k: Any) -> dict[str, Any] | None:
        calls["n"] += 1
        return None

    monkeypatch.setattr(openverse, "http_get_json", _json)
    openverse.note_openverse_transient(seconds=60)
    with pytest.raises(openverse.PlacesTransientError):
        openverse.lookup_openverse_image_url("Nijo Castle", city="Kyoto")
    assert calls["n"] == 0
    openverse.clear_openverse_backoff_for_tests()


def test_resolve_openverse_photo_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    openverse.clear_openverse_backoff_for_tests()

    def _json(_url: str, **_k: Any) -> dict[str, Any] | None:
        return {
            "results": [
                {
                    "thumbnail": "https://api.openverse.org/v1/images/x/thumb/",
                    "url": "https://live.staticflickr.com/x.jpg",
                }
            ]
        }

    monkeypatch.setattr(openverse, "http_get_json", _json)
    monkeypatch.setattr(
        openverse,
        "payload_from_image_url",
        lambda url, **_k: {
            "photo_url": url,
            "places_photo_name": None,
            "photo_data_url": "data:image/jpeg;base64,ov",
        },
    )
    payload = openverse.resolve_openverse_photo_payload("Nijo Castle", city="Kyoto")
    assert payload["photo_url"] == "https://api.openverse.org/v1/images/x/thumb/"
    assert payload["photo_data_url"] == "data:image/jpeg;base64,ov"


def test_get_place_photo_uses_wikidata_when_wikipedia_empty(
    dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from db import repository as repo
    from places.image_fallback import clear_wikipedia_backoff_for_tests
    from places.openverse_fallback import clear_openverse_backoff_for_tests
    from places.photo_cache import clear_cache_for_tests
    from places.wikidata_fallback import clear_wikidata_backoff_for_tests
    from routes import places as places_routes

    clear_cache_for_tests()
    clear_wikipedia_backoff_for_tests()
    clear_wikidata_backoff_for_tests()
    clear_openverse_backoff_for_tests()

    user = "user-wd-1"
    trip = "trip-wd-1"
    repo.put_trip(
        user_sub=user,
        trip_id=trip,
        origin="Chicago",
        destination="Japan",
        destination_type="country",
        start_date="2026-09-01",
        end_date="2026-09-07",
        day_count=7,
        preferences="",
        table=dynamodb_table,
    )
    repo.put_day(
        user_sub=user,
        trip_id=trip,
        day={
            "day_index": 1,
            "date": "2026-09-01",
            "city": "Kyoto",
            "overnight_city": "Kyoto",
            "theme": "Castles",
            "places": [
                {
                    "name": "Nijo Castle",
                    "place_key": "nijo",
                    "place_id": "ChIJ1234567890abcd",
                }
            ],
            "notes": "",
        },
        table=dynamodb_table,
    )
    empty = {
        "photo_url": None,
        "places_photo_name": None,
        "photo_data_url": None,
    }
    monkeypatch.setattr(places_routes, "places_api_key_from_env", lambda: "test-key")
    monkeypatch.setattr(
        places_routes,
        "resolve_place_photo_payload",
        lambda **_k: dict(empty),
    )
    monkeypatch.setattr(
        places_routes,
        "resolve_wikipedia_photo_payload",
        lambda *_a, **_k: dict(empty),
    )
    monkeypatch.setattr(
        places_routes,
        "resolve_wikidata_photo_payload",
        lambda *_a, **_k: {
            "photo_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Nijo_Castle.jpg?width=640",
            "places_photo_name": None,
            "photo_data_url": "data:image/jpeg;base64,wd",
        },
    )
    monkeypatch.setattr(
        places_routes,
        "resolve_openverse_photo_payload",
        lambda *_a, **_k: dict(empty),
    )
    result = places_routes.get_place_photo(
        {
            "queryStringParameters": {
                "trip_id": trip,
                "place_key": "nijo",
            }
        },
        user,
    )
    assert result["photo_data_url"] == "data:image/jpeg;base64,wd"


def test_get_place_photo_uses_openverse_last(
    dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from db import repository as repo
    from places.image_fallback import clear_wikipedia_backoff_for_tests
    from places.openverse_fallback import clear_openverse_backoff_for_tests
    from places.photo_cache import clear_cache_for_tests
    from places.wikidata_fallback import clear_wikidata_backoff_for_tests
    from routes import places as places_routes

    clear_cache_for_tests()
    clear_wikipedia_backoff_for_tests()
    clear_wikidata_backoff_for_tests()
    clear_openverse_backoff_for_tests()

    user = "user-ov-1"
    trip = "trip-ov-1"
    repo.put_trip(
        user_sub=user,
        trip_id=trip,
        origin="Chicago",
        destination="Japan",
        destination_type="country",
        start_date="2026-09-01",
        end_date="2026-09-07",
        day_count=7,
        preferences="",
        table=dynamodb_table,
    )
    repo.put_day(
        user_sub=user,
        trip_id=trip,
        day={
            "day_index": 1,
            "date": "2026-09-01",
            "city": "Kyoto",
            "overnight_city": "Kyoto",
            "theme": "Food",
            "places": [
                {
                    "name": "Obscure Alley Stall",
                    "place_key": "obscure",
                    "place_id": "ChIJ1234567890abcd",
                }
            ],
            "notes": "",
        },
        table=dynamodb_table,
    )
    empty = {
        "photo_url": None,
        "places_photo_name": None,
        "photo_data_url": None,
    }
    monkeypatch.setattr(places_routes, "places_api_key_from_env", lambda: "test-key")
    monkeypatch.setattr(
        places_routes, "resolve_place_photo_payload", lambda **_k: dict(empty)
    )
    monkeypatch.setattr(
        places_routes, "resolve_wikipedia_photo_payload", lambda *_a, **_k: dict(empty)
    )
    monkeypatch.setattr(
        places_routes, "resolve_wikidata_photo_payload", lambda *_a, **_k: dict(empty)
    )
    monkeypatch.setattr(
        places_routes,
        "resolve_openverse_photo_payload",
        lambda *_a, **_k: {
            "photo_url": "https://api.openverse.org/v1/images/x/thumb/",
            "places_photo_name": None,
            "photo_data_url": "data:image/jpeg;base64,ov",
        },
    )
    result = places_routes.get_place_photo(
        {
            "queryStringParameters": {
                "trip_id": trip,
                "place_key": "obscure",
            }
        },
        user,
    )
    assert result["photo_data_url"] == "data:image/jpeg;base64,ov"
