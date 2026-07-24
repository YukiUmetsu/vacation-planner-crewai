"""Tests for Wikipedia landmark image fallback."""

from __future__ import annotations

from typing import Any

import pytest

from services import place_image_fallback as wiki


def test_candidate_titles_include_city() -> None:
    titles = wiki._candidate_titles("Meiji Shrine", "Tokyo")
    assert "Meiji Shrine" in titles
    assert "Meiji Shrine (Tokyo)" in titles


def test_resolve_wikipedia_photo_payload_with_thumbnail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _json(url: str) -> dict[str, Any] | None:
        if "page/summary" in url:
            return {
                "type": "standard",
                "thumbnail": {
                    "source": "https://upload.wikimedia.org/example.jpg",
                },
            }
        return None

    monkeypatch.setattr(wiki, "_http_get_json", _json)
    monkeypatch.setattr(
        wiki,
        "_http_get_bytes",
        lambda _url: (b"\xff\xd8\xff", "image/jpeg"),
    )
    payload = wiki.resolve_wikipedia_photo_payload("Meiji Shrine", city="Tokyo")
    assert payload["photo_url"] == "https://upload.wikimedia.org/example.jpg"
    assert payload["photo_data_url"] is not None
    assert payload["photo_data_url"].startswith("data:image/jpeg;base64,")


def test_resolve_wikipedia_photo_payload_empty_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wiki, "_http_get_json", lambda _url: None)
    monkeypatch.setattr(wiki, "_search_title", lambda _q: None)
    payload = wiki.resolve_wikipedia_photo_payload("Obscure Alley Stall", city="Tokyo")
    assert payload["photo_url"] is None
    assert payload["photo_data_url"] is None


def test_get_place_photo_uses_wikipedia_when_places_empty(
    dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from db import repository as repo
    from routes import places as places_routes

    user = "user-wiki-1"
    trip = "trip-wiki-1"
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
                    "place_id": "ChIJ1234567890abcd",
                }
            ],
            "notes": "",
        },
        table=dynamodb_table,
    )
    monkeypatch.setattr(places_routes, "places_api_key_from_env", lambda: "test-key")
    monkeypatch.setattr(
        places_routes,
        "resolve_place_photo_payload",
        lambda **_kwargs: {
            "photo_url": None,
            "places_photo_name": None,
            "photo_data_url": None,
        },
    )
    monkeypatch.setattr(
        places_routes,
        "resolve_wikipedia_photo_payload",
        lambda *_a, **_k: {
            "photo_url": "https://upload.wikimedia.org/meiji.jpg",
            "places_photo_name": None,
            "photo_data_url": "data:image/jpeg;base64,abc",
        },
    )
    # Skip enrich — already has a usable Google id.
    result = places_routes.get_place_photo(
        {
            "queryStringParameters": {
                "trip_id": trip,
                "place_key": "meiji",
            }
        },
        user,
    )
    assert result["photo_data_url"] == "data:image/jpeg;base64,abc"
    assert result["photo_url"] == "https://upload.wikimedia.org/meiji.jpg"
