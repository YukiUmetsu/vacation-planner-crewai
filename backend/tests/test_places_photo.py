"""Tests for Places photo name normalization and resolve helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from db import repository as repo
from http_utils import ApiError
from routes import places as places_routes
from services.places_client import (
    normalize_place_id,
    normalize_places_photo_name,
    is_usable_google_place_id,
    resolve_place_photo_uri,
)
from services.place_photo_cache import clear_cache_for_tests

USER = "user-photo-1"
TRIP = "trip-photo-1"
PHOTO_NAME = "places/ChIJ1234567890/photos/AaBb"
PLACE_ID = "ChIJ1234567890"
PLACE_KEY = "cafe|tokyo"


def test_normalize_places_photo_name() -> None:
    assert (
        normalize_places_photo_name("places/ChIJ123/photos/AaBbCc")
        == "places/ChIJ123/photos/AaBbCc"
    )
    assert normalize_places_photo_name("/places/ChIJ123/photos/AaBbCc") == (
        "places/ChIJ123/photos/AaBbCc"
    )
    assert (
        normalize_places_photo_name("places/ChIJ123/photos/AaBbCc/media")
        == "places/ChIJ123/photos/AaBbCc"
    )
    assert normalize_places_photo_name("https://evil.example/x") is None
    assert normalize_places_photo_name("places/../photos/x") is None
    assert normalize_places_photo_name("") is None


def test_normalize_place_id() -> None:
    assert normalize_place_id("ChIJN1t_tDeuEmsRUsoyG83frY4") == (
        "ChIJN1t_tDeuEmsRUsoyG83frY4"
    )
    assert normalize_place_id("places/ChIJN1t_tDeuEmsRUsoyG83frY4") == (
        "ChIJN1t_tDeuEmsRUsoyG83frY4"
    )
    assert normalize_place_id("not a place") is None


def test_is_usable_google_place_id_rejects_crew_slugs() -> None:
    assert is_usable_google_place_id("ChIJN1t_tDeuEmsRUsoyG83frY4")
    assert not is_usable_google_place_id(
        "teamlab-borderless", place_key="teamlab-borderless"
    )
    assert not is_usable_google_place_id("asakusa_senso_ji")
    assert not is_usable_google_place_id("1")
    assert not is_usable_google_place_id("some-slug-name")


def test_resolve_place_photo_uri_uses_photo_name() -> None:
    client = MagicMock()
    client.photo_media_uri.return_value = "https://lh3.googleusercontent.com/p.jpg"
    uri, name = resolve_place_photo_uri(
        photo_name="places/ChIJ123/photos/AaBb",
        client=client,
    )
    assert uri == "https://lh3.googleusercontent.com/p.jpg"
    assert name == "places/ChIJ123/photos/AaBb"
    client.photo_media_uri.assert_called_once()
    client.first_photo_name_for_place_id.assert_not_called()


def test_resolve_place_photo_uri_falls_back_to_place_id() -> None:
    client = MagicMock()
    client.first_photo_name_for_place_id.return_value = (
        "places/ChIJ123/photos/AaBb"
    )
    client.photo_media_uri.return_value = "https://lh3.googleusercontent.com/p.jpg"
    uri, name = resolve_place_photo_uri(
        place_id="ChIJ123",
        client=client,
    )
    assert uri == "https://lh3.googleusercontent.com/p.jpg"
    assert name == "places/ChIJ123/photos/AaBb"


def test_resolve_place_photo_payload_uses_legacy_when_new_api_has_no_photos() -> None:
    from services.places_client import resolve_place_photo_payload

    client = MagicMock()
    client.first_photo_name_for_place_id.return_value = None
    client.fetch_legacy_photo_bytes.return_value = (
        b"\xff\xd8\xff",
        "image/jpeg",
        "https://lh3.googleusercontent.com/legacy.jpg",
    )
    payload = resolve_place_photo_payload(
        place_id="ChIJ1234567890",
        client=client,
        include_bytes=True,
    )
    assert payload["photo_data_url"] is not None
    assert payload["photo_data_url"].startswith("data:image/jpeg;base64,")
    assert payload["photo_url"] == "https://lh3.googleusercontent.com/legacy.jpg"
    client.fetch_legacy_photo_bytes.assert_called_once()


def _seed_owned_place(table: Any, *, with_photo_refs: bool = True) -> None:
    repo.put_trip(
        user_sub=USER,
        trip_id=TRIP,
        origin="Chicago",
        destination="Japan",
        destination_type="country",
        start_date="2026-09-01",
        end_date="2026-09-07",
        day_count=7,
        preferences="",
        table=table,
    )
    place: dict[str, Any] = {
        "name": "Cafe",
        "place_key": PLACE_KEY,
    }
    if with_photo_refs:
        place["place_id"] = PLACE_ID
        place["places_photo_name"] = PHOTO_NAME
    repo.put_day(
        user_sub=USER,
        trip_id=TRIP,
        day={
            "day_index": 1,
            "date": "2026-09-01",
            "city": "Tokyo",
            "overnight_city": "Tokyo",
            "theme": "Arrival",
            "places": [place],
            "notes": "",
        },
        table=table,
    )


def test_get_place_photo_requires_trip_id() -> None:
    with pytest.raises(ApiError) as exc:
        places_routes.get_place_photo(
            {"queryStringParameters": {"place_id": PLACE_ID}},
            USER,
        )
    assert exc.value.status_code == 400
    assert "trip_id" in exc.value.message


def test_get_place_photo_rejects_unowned_ref(
    dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    clear_cache_for_tests()
    _seed_owned_place(dynamodb_table)
    monkeypatch.setattr(places_routes, "places_api_key_from_env", lambda: "test-key")
    monkeypatch.setattr(
        places_routes,
        "resolve_place_photo_payload",
        lambda **kwargs: {
            "photo_url": "https://cdn.example/p.jpg",
            "places_photo_name": PHOTO_NAME,
            "photo_data_url": "data:image/jpeg;base64,abc",
        },
    )
    with pytest.raises(ApiError) as exc:
        places_routes.get_place_photo(
            {
                "queryStringParameters": {
                    "trip_id": TRIP,
                    "place_id": "ChIJnotOwned99",
                }
            },
            USER,
        )
    assert exc.value.status_code == 403
    assert exc.value.code == "photo_forbidden"


def test_get_place_photo_returns_data_url(
    dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    clear_cache_for_tests()
    _seed_owned_place(dynamodb_table)
    captured: dict[str, Any] = {}
    monkeypatch.setattr(places_routes, "places_api_key_from_env", lambda: "test-key")

    def _resolve(**kwargs: Any) -> dict[str, str | None]:
        captured.update(kwargs)
        return {
            "photo_url": "https://cdn.example/p.jpg",
            "places_photo_name": PHOTO_NAME,
            "photo_data_url": "data:image/jpeg;base64,/9j/4AAQ",
        }

    monkeypatch.setattr(places_routes, "resolve_place_photo_payload", _resolve)
    result = places_routes.get_place_photo(
        {
            "queryStringParameters": {
                "trip_id": TRIP,
                "place_key": PLACE_KEY,
            }
        },
        USER,
    )
    assert result["photo_data_url"] == "data:image/jpeg;base64,/9j/4AAQ"
    assert result["photo_url"] == "https://cdn.example/p.jpg"
    assert captured.get("place_id") == PLACE_ID
    assert captured.get("photo_name") == PHOTO_NAME


def test_get_place_photo_enriches_when_refs_missing(
    dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    clear_cache_for_tests()
    _seed_owned_place(dynamodb_table, with_photo_refs=False)
    monkeypatch.setattr(places_routes, "places_api_key_from_env", lambda: "test-key")

    def _enrich(
        place: dict[str, Any], *, overnight_city: str = "", **_kwargs: Any
    ) -> dict[str, Any]:
        assert overnight_city == "Tokyo"
        return {
            **place,
            "place_id": PLACE_ID,
            "places_photo_name": PHOTO_NAME,
        }

    monkeypatch.setattr(places_routes, "enrich_place", _enrich)
    monkeypatch.setattr(
        places_routes,
        "resolve_place_photo_payload",
        lambda **kwargs: {
            "photo_url": "https://cdn.example/p.jpg",
            "places_photo_name": PHOTO_NAME,
            "photo_data_url": "data:image/jpeg;base64,abc",
        },
    )
    result = places_routes.get_place_photo(
        {
            "queryStringParameters": {
                "trip_id": TRIP,
                "place_key": PLACE_KEY,
            }
        },
        USER,
    )
    assert result["photo_data_url"] == "data:image/jpeg;base64,abc"


def test_get_place_photo_looks_up_when_place_id_is_crew_slug(
    dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Crews often set place_id=place_key; that must not block Text Search."""
    clear_cache_for_tests()
    repo.put_trip(
        user_sub=USER,
        trip_id=TRIP,
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
        user_sub=USER,
        trip_id=TRIP,
        day={
            "day_index": 1,
            "date": "2026-09-01",
            "city": "Tokyo",
            "overnight_city": "Tokyo",
            "theme": "Arrival",
            "places": [
                {
                    "name": "TeamLab Borderless",
                    "place_key": "teamlab-borderless",
                    "place_id": "teamlab-borderless",
                }
            ],
            "notes": "",
        },
        table=dynamodb_table,
    )
    monkeypatch.setattr(places_routes, "places_api_key_from_env", lambda: "test-key")

    def _enrich(
        place: dict[str, Any], *, overnight_city: str = "", **_kwargs: Any
    ) -> dict[str, Any]:
        assert "place_id" not in place or not place.get("place_id")
        assert overnight_city == "Tokyo"
        return {
            **place,
            "place_id": PLACE_ID,
            "places_photo_name": PHOTO_NAME,
        }

    monkeypatch.setattr(places_routes, "enrich_place", _enrich)
    monkeypatch.setattr(
        places_routes,
        "resolve_place_photo_payload",
        lambda **kwargs: {
            "photo_url": "https://cdn.example/p.jpg",
            "places_photo_name": PHOTO_NAME,
            "photo_data_url": "data:image/jpeg;base64,abc",
        },
    )
    result = places_routes.get_place_photo(
        {
            "queryStringParameters": {
                "trip_id": TRIP,
                "place_key": "teamlab-borderless",
            }
        },
        USER,
    )
    assert result["photo_data_url"] == "data:image/jpeg;base64,abc"


def test_get_place_photo_falls_back_when_places_key_missing(
    dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    clear_cache_for_tests()
    _seed_owned_place(dynamodb_table)
    monkeypatch.setattr(places_routes, "places_api_key_from_env", lambda: "")
    monkeypatch.setattr(
        places_routes,
        "resolve_wikipedia_photo_payload",
        lambda *_a, **_k: {
            "photo_url": None,
            "places_photo_name": None,
            "photo_data_url": None,
        },
    )
    with pytest.raises(ApiError) as exc:
        places_routes.get_place_photo(
            {
                "queryStringParameters": {
                    "trip_id": TRIP,
                    "place_key": PLACE_KEY,
                }
            },
            USER,
        )
    assert exc.value.status_code == 404
    assert exc.value.code == "photo_not_found"
