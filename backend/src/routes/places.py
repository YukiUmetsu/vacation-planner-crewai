"""Places photo resolve (Google Places media → CDN URI / data URL)."""

from __future__ import annotations

import logging
from typing import Any

from db import repository as repo
from http_utils import ApiError
from services.place_image_fallback import (
    resolve_cached_stable_photo_payload,
    resolve_wikipedia_photo_payload,
)
from services.place_photo_cache import (
    cache_key,
    get_cached_payload,
    is_fresh_photo_miss,
    is_negative_cached,
    is_stable_photo_url,
    lookup_key,
    persist_place_photo_fields,
    places_photo_name_is_stale,
    set_cached_payload,
    set_negative_cached,
)
from services.places_client import (
    is_usable_google_place_id,
    normalize_place_id,
    normalize_places_photo_name,
    places_api_key_from_env,
    resolve_place_photo_payload,
)
from services.places_enrich import enrich_place

logger = logging.getLogger(__name__)


def _query_param(qs: dict[str, Any], key: str) -> str | None:
    value = qs.get(key)
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _trip_places(
    user_sub: str, trip_id: str
) -> tuple[bool, list[dict[str, Any]]]:
    """Return (has_trip, places) with overnight city + day_index for enrich/cache."""
    items = repo.get_trip_bundle(user_sub=user_sub, trip_id=trip_id)
    has_trip = False
    places: list[dict[str, Any]] = []
    for item in items:
        if item.get("entity_type") == "TRIP":
            has_trip = True
        if item.get("entity_type") != "DAY":
            continue
        city = str(
            item.get("overnight_city") or item.get("city") or ""
        ).strip()
        try:
            day_index = int(item.get("day_index") or 0)
        except (TypeError, ValueError):
            day_index = 0
        raw = item.get("places") or []
        if not isinstance(raw, list):
            continue
        for place in raw:
            if isinstance(place, dict):
                places.append(
                    {
                        **place,
                        "_overnight_city": city,
                        "_day_index": day_index,
                    }
                )
    return has_trip, places


def _match_owned_place(
    places: list[dict[str, Any]],
    *,
    photo_name: str | None,
    place_id: str | None,
    place_key: str | None,
) -> dict[str, Any] | None:
    """Find a day place that matches the client request (owned-trip only)."""
    want_name = normalize_places_photo_name(photo_name)
    want_id = normalize_place_id(place_id)
    want_key = (place_key or "").strip()

    for place in places:
        stored_name = normalize_places_photo_name(
            str(place.get("places_photo_name") or "") or None
        )
        stored_id = normalize_place_id(str(place.get("place_id") or "") or None)
        stored_key = str(place.get("place_key") or "").strip()
        if want_key and stored_key and want_key == stored_key:
            return place
        if want_id and stored_id and want_id == stored_id:
            return place
        if want_name and stored_name and want_name == stored_name:
            return place
    return None


def _ensure_photo_refs(place: dict[str, Any]) -> dict[str, Any]:
    """Fill Google place_id via Text Search when missing (slug / placeholder ids)."""
    if is_stable_photo_url(str(place.get("photo_url") or "") or None):
        return place
    has_google_id = is_usable_google_place_id(
        str(place.get("place_id") or "") or None,
        place_key=str(place.get("place_key") or "") or None,
    )
    if has_google_id:
        # Place Details / legacy photo can use place_id — skip Text Search.
        return place

    city = str(place.get("_overnight_city") or "").strip()
    cleaned = {**place}
    cleaned.pop("place_id", None)
    return enrich_place(cleaned, overnight_city=city, loose_match=True)


def _day_index(place: dict[str, Any]) -> int:
    try:
        return int(place.get("_day_index") or 0)
    except (TypeError, ValueError):
        return 0


def get_place_photo(event: dict[str, Any], user_sub: str) -> dict[str, Any]:
    """Resolve a place photo for a venue already on the caller's trip.

    Requires ``trip_id`` plus at least one of ``place_key``, ``photo_name``, or
    ``place_id``. Optional ``refresh=1`` bypasses durable miss / stable URL.

    Durable cache lives on the DAY place object (``photo_url``, ``photo_status``,
    …). Process cache only dedupes short-lived requests.
    """
    qs = event.get("queryStringParameters") or {}
    if not isinstance(qs, dict):
        qs = {}
    trip_id = _query_param(qs, "trip_id")
    photo_name = _query_param(qs, "photo_name")
    place_id = _query_param(qs, "place_id")
    place_key = _query_param(qs, "place_key")
    refresh = (_query_param(qs, "refresh") or "").lower() in {"1", "true", "yes"}
    if not trip_id:
        raise ApiError(400, "trip_id is required", code="validation_error")
    if not photo_name and not place_id and not place_key:
        raise ApiError(
            400,
            "place_key, photo_name, or place_id is required",
            code="validation_error",
        )

    has_trip, places = _trip_places(user_sub, trip_id)
    if not has_trip:
        raise ApiError(404, "Trip not found", code="not_found")

    owned = _match_owned_place(
        places,
        photo_name=photo_name,
        place_id=place_id,
        place_key=place_key,
    )
    if owned is None:
        raise ApiError(
            403,
            "Photo is not linked to a place on this trip",
            code="photo_forbidden",
        )

    city = str(owned.get("_overnight_city") or "").strip()
    pk = str(owned.get("place_key") or place_key or "").strip()
    place_name = str(owned.get("name") or "")
    mem_key = cache_key(
        trip_id=trip_id,
        place_key=pk,
        name=place_name,
        city=city,
    )
    miss_key = lookup_key(name=place_name, city=city)
    day_index = _day_index(owned)

    if not refresh:
        cached = get_cached_payload(mem_key)
        if cached and (cached.get("photo_data_url") or cached.get("photo_url")):
            return {
                "photo_url": cached.get("photo_url"),
                "places_photo_name": cached.get("places_photo_name"),
                "photo_data_url": cached.get("photo_data_url"),
            }

        if is_negative_cached(mem_key) or is_negative_cached(miss_key):
            raise ApiError(
                404,
                "No photo available for this place",
                code="photo_not_found",
            )

        if is_fresh_photo_miss(owned):
            raise ApiError(
                404,
                "No photo available for this place",
                code="photo_not_found",
            )

        stored_url = str(owned.get("photo_url") or "").strip() or None
        if is_stable_photo_url(stored_url):
            payload = resolve_cached_stable_photo_payload(
                stored_url or "",
                places_photo_name=str(owned.get("places_photo_name") or "").strip()
                or None,
                include_bytes=False,
            )
            set_cached_payload(mem_key, payload)
            return payload

    owned = _ensure_photo_refs(owned)
    stored_photo_name = str(owned.get("places_photo_name") or "").strip() or None
    if stored_photo_name and places_photo_name_is_stale(owned):
        # Force Details refresh via place_id path.
        stored_photo_name = None
    raw_place_id = str(owned.get("place_id") or "").strip() or None
    stored_place_id = (
        raw_place_id
        if is_usable_google_place_id(
            raw_place_id, place_key=str(owned.get("place_key") or "") or None
        )
        else None
    )
    has_places_key = bool(places_api_key_from_env())
    payload: dict[str, Any] = {
        "photo_url": None,
        "places_photo_name": None,
        "photo_data_url": None,
    }
    if has_places_key and (stored_photo_name or stored_place_id):
        payload = resolve_place_photo_payload(
            photo_name=stored_photo_name,
            place_id=stored_place_id,
            include_bytes=True,
        )

    if not payload.get("photo_data_url") and not payload.get("photo_url"):
        wiki = resolve_wikipedia_photo_payload(
            place_name,
            city=city,
            include_bytes=False,
        )
        if wiki.get("photo_data_url") or wiki.get("photo_url"):
            logger.info(
                "photo resolve: wikipedia fallback name=%r city=%r",
                place_name,
                city or None,
            )
            payload = wiki

    resolved_place_id = stored_place_id or (
        str(owned.get("place_id") or "").strip()
        if is_usable_google_place_id(
            str(owned.get("place_id") or "") or None,
            place_key=pk or None,
        )
        else None
    )

    if not payload.get("photo_data_url") and not payload.get("photo_url"):
        set_negative_cached(mem_key, miss_key)
        persist_place_photo_fields(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            place_key=pk,
            place_id=resolved_place_id,
            photo_status="none",
        )
        if not has_places_key and not stored_photo_name and not stored_place_id:
            raise ApiError(
                503,
                "Google Places is not configured (set GOOGLE_PLACES_API_KEY or GOOGLE_PLACES_SECRET_ARN)",
                code="places_not_configured",
            )
        logger.info(
            "photo resolve: no image name=%r place_key=%r place_id=%r",
            place_name,
            owned.get("place_key"),
            (stored_place_id or "")[:32] or None,
        )
        raise ApiError(
            404,
            "No photo available for this place",
            code="photo_not_found",
        )

    set_cached_payload(mem_key, payload)
    persist_place_photo_fields(
        user_sub=user_sub,
        trip_id=trip_id,
        day_index=day_index,
        place_key=pk,
        photo_url=str(payload.get("photo_url") or "") or None,
        place_id=resolved_place_id,
        places_photo_name=str(payload.get("places_photo_name") or "") or None,
        photo_status="ok",
    )

    return {
        "photo_url": payload.get("photo_url"),
        "places_photo_name": payload.get("places_photo_name"),
        "photo_data_url": payload.get("photo_data_url"),
    }
