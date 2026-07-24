"""Tests for place photo URL caching helpers and durable miss TTL."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from db import repository as repo
from http_utils import ApiError
from routes import places as places_routes
from services.place_photo_cache import (
    cache_key,
    clear_cache_for_tests,
    get_cached_payload,
    is_fresh_photo_miss,
    is_negative_cached,
    is_stable_photo_url,
    lookup_key,
    places_photo_name_is_stale,
    set_cached_payload,
    set_negative_cached,
)


def test_stable_photo_url_detects_wikimedia() -> None:
    assert is_stable_photo_url(
        "https://upload.wikimedia.org/wikipedia/commons/a/a1/Meiji.jpg"
    )
    assert not is_stable_photo_url("https://lh3.googleusercontent.com/p/AF1Qip")
    assert not is_stable_photo_url("")


def test_memory_cache_roundtrip_drops_stable_data_url() -> None:
    clear_cache_for_tests()
    key = cache_key(trip_id="t1", place_key="meiji")
    assert get_cached_payload(key) is None
    set_cached_payload(
        key,
        {
            "photo_url": "https://upload.wikimedia.org/x.jpg",
            "places_photo_name": None,
            "photo_data_url": "data:image/jpeg;base64,abc",
        },
    )
    hit = get_cached_payload(key)
    assert hit is not None
    assert hit["photo_url"] == "https://upload.wikimedia.org/x.jpg"
    assert hit["photo_data_url"] is None
    clear_cache_for_tests()


def test_negative_cache() -> None:
    clear_cache_for_tests()
    key = lookup_key(name="Obscure Alley", city="Tokyo")
    assert not is_negative_cached(key)
    set_negative_cached(key)
    assert is_negative_cached(key)
    clear_cache_for_tests()


def test_fresh_photo_miss_ttl() -> None:
    now = datetime.now(timezone.utc)
    assert is_fresh_photo_miss(
        {
            "photo_status": "none",
            "photo_checked_at": now.isoformat(),
        }
    )
    assert not is_fresh_photo_miss({"photo_status": "ok"})
    old = (now - timedelta(days=8)).isoformat()
    assert not is_fresh_photo_miss(
        {"photo_status": "none", "photo_checked_at": old}
    )


def test_places_photo_name_stale() -> None:
    now = datetime.now(timezone.utc)
    assert places_photo_name_is_stale({"places_photo_name": ""})
    assert not places_photo_name_is_stale(
        {
            "places_photo_name": "places/ChIJ/photos/x",
            "photo_checked_at": now.isoformat(),
        }
    )
    old = (now - timedelta(days=8)).isoformat()
    assert places_photo_name_is_stale(
        {
            "places_photo_name": "places/ChIJ/photos/x",
            "photo_checked_at": old,
        }
    )


def test_get_place_photo_serves_stable_url_without_externals(
    dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    clear_cache_for_tests()
    user = "user-cache-1"
    trip = "trip-cache-1"
    wiki = "https://upload.wikimedia.org/wikipedia/commons/m.jpg"
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
            "city": "Tokyo",
            "overnight_city": "Tokyo",
            "theme": "Shrines",
            "places": [
                {
                    "name": "Meiji Shrine",
                    "place_key": "meiji",
                    "photo_url": wiki,
                    "photo_status": "ok",
                }
            ],
            "notes": "",
        },
        table=dynamodb_table,
    )

    def _boom(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("should not call Places")

    monkeypatch.setattr(places_routes, "resolve_place_photo_payload", _boom)
    monkeypatch.setattr(places_routes, "resolve_wikipedia_photo_payload", _boom)
    monkeypatch.setattr(places_routes, "places_api_key_from_env", lambda: "key")

    result = places_routes.get_place_photo(
        {
            "queryStringParameters": {
                "trip_id": trip,
                "place_key": "meiji",
            }
        },
        user,
    )
    assert result["photo_url"] == wiki
    assert result.get("photo_data_url") in (None, "")


def test_get_place_photo_respects_durable_miss(
    dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    clear_cache_for_tests()
    user = "user-cache-2"
    trip = "trip-cache-2"
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
            "city": "Tokyo",
            "overnight_city": "Tokyo",
            "theme": "Alleys",
            "places": [
                {
                    "name": "Obscure Alley",
                    "place_key": "obscure",
                    "photo_status": "none",
                    "photo_checked_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
            "notes": "",
        },
        table=dynamodb_table,
    )
    def _no_places(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("should not call Places")

    def _no_wiki(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise AssertionError("should not call Wikipedia")

    monkeypatch.setattr(places_routes, "resolve_place_photo_payload", _no_places)
    monkeypatch.setattr(places_routes, "resolve_wikipedia_photo_payload", _no_wiki)
    with pytest.raises(ApiError) as exc:
        places_routes.get_place_photo(
            {
                "queryStringParameters": {
                    "trip_id": trip,
                    "place_key": "obscure",
                }
            },
            user,
        )
    assert exc.value.status_code == 404
    assert exc.value.code == "photo_not_found"
