"""Places photo resolve (Google Places media → CDN URI / data URL)."""

from __future__ import annotations

import logging
from typing import Any

from db import repository as repo
from http_utils import ApiError
from places.client import (
    PlacesTransientError,
    is_usable_google_place_id,
    note_places_transient,
    normalize_place_id,
    normalize_places_photo_name,
    places_api_key_from_env,
    places_lookup_in_backoff,
    resolve_place_photo_payload,
)
from places.enrich import enrich_place
from places.image_fallback import (
    note_wikipedia_transient,
    resolve_cached_stable_photo_payload,
    resolve_wikipedia_photo_payload,
    wikipedia_lookup_in_backoff,
)
from places.openverse_fallback import (
    note_openverse_transient,
    openverse_lookup_in_backoff,
    resolve_openverse_photo_payload,
)
from places.photo_cache import (
    cache_key,
    get_cached_payload,
    is_fresh_photo_miss,
    is_negative_cached,
    is_persistable_photo_url,
    is_stable_photo_url,
    lookup_key,
    persist_place_photo_fields,
    places_photo_name_is_stale,
    set_cached_payload,
    set_negative_cached,
)
from places.wikidata_fallback import (
    note_wikidata_transient,
    resolve_wikidata_photo_payload,
    wikidata_lookup_in_backoff,
)
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
    stored = str(place.get("photo_url") or "") or None
    if is_stable_photo_url(stored) or (
        is_persistable_photo_url(stored)
        and str(place.get("photo_status") or "").strip().lower() == "ok"
    ):
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
            # Durable miss without a confirmed Google place_id is often a stale
            # rate-limit poison — allow another resolve attempt.
            has_google = is_usable_google_place_id(
                str(owned.get("place_id") or "") or None,
                place_key=str(owned.get("place_key") or "") or None,
            )
            if has_google:
                raise ApiError(
                    404,
                    "No photo available for this place",
                    code="photo_not_found",
                )

        stored_url = str(owned.get("photo_url") or "").strip() or None
        if is_stable_photo_url(stored_url) or (
            is_persistable_photo_url(stored_url)
            and str(owned.get("photo_status") or "").strip().lower() == "ok"
        ):
            # Include bytes so the SPA can render without hotlinking CDNs
            # (Arc / tracking blockers often fail bare third-party <img>).
            payload = resolve_cached_stable_photo_payload(
                stored_url or "",
                places_photo_name=str(owned.get("places_photo_name") or "").strip()
                or None,
                include_bytes=True,
            )
            set_cached_payload(mem_key, payload)
            return payload

    # refresh=1 still prefers a known-good durable URL after a failed re-resolve below.
    prior_stable_url = str(owned.get("photo_url") or "").strip() or None
    if not (
        is_stable_photo_url(prior_stable_url)
        or is_persistable_photo_url(prior_stable_url)
    ):
        prior_stable_url = None

    transient = False
    has_places_key = bool(places_api_key_from_env())
    payload: dict[str, Any] = {
        "photo_url": None,
        "places_photo_name": None,
        "photo_data_url": None,
    }

    def _google_refs(place: dict[str, Any]) -> tuple[str | None, str | None]:
        photo = str(place.get("places_photo_name") or "").strip() or None
        if photo and places_photo_name_is_stale(place):
            photo = None
        raw_id = str(place.get("place_id") or "").strip() or None
        gid = (
            raw_id
            if is_usable_google_place_id(
                raw_id, place_key=str(place.get("place_key") or "") or None
            )
            else None
        )
        return photo, gid

    stored_photo_name, stored_place_id = _google_refs(owned)

    def _note_transient(exc: PlacesTransientError, *, what: str) -> None:
        nonlocal transient
        transient = True
        # Keep provider backoffs separate so one 429 does not redirect traffic
        # onto another already-stressed public API.
        if what == "wikipedia":
            note_wikipedia_transient()
        elif what == "wikidata":
            note_wikidata_transient()
        elif what == "openverse":
            note_openverse_transient()
        else:
            note_places_transient()
        logger.warning(
            "photo %s transient name=%r status=%s: %s",
            what,
            place_name,
            getattr(exc, "status", None),
            exc,
        )

    def _try_google_payload() -> None:
        nonlocal payload, stored_photo_name, stored_place_id
        if not (has_places_key and (stored_photo_name or stored_place_id)):
            return
        try:
            payload = resolve_place_photo_payload(
                photo_name=stored_photo_name,
                place_id=stored_place_id,
                include_bytes=True,
            )
        except PlacesTransientError as exc:
            _note_transient(exc, what="google")

    def _try_wikipedia() -> None:
        nonlocal payload, transient
        if payload.get("photo_data_url") or payload.get("photo_url"):
            return
        if wikipedia_lookup_in_backoff():
            transient = True
            logger.info(
                "photo resolve: wikipedia skipped (backoff) name=%r",
                place_name,
            )
            return
        try:
            wiki = resolve_wikipedia_photo_payload(
                place_name,
                city=city,
                include_bytes=True,
            )
            if wiki.get("photo_data_url") or wiki.get("photo_url"):
                logger.info(
                    "photo resolve: wikipedia fallback name=%r city=%r",
                    place_name,
                    city or None,
                )
                payload = wiki
        except PlacesTransientError as exc:
            _note_transient(exc, what="wikipedia")

    def _try_wikidata() -> None:
        nonlocal payload, transient
        if payload.get("photo_data_url") or payload.get("photo_url"):
            return
        if wikidata_lookup_in_backoff():
            transient = True
            logger.info(
                "photo resolve: wikidata skipped (backoff) name=%r",
                place_name,
            )
            return
        try:
            wd = resolve_wikidata_photo_payload(
                place_name,
                city=city,
                include_bytes=True,
            )
            if wd.get("photo_data_url") or wd.get("photo_url"):
                logger.info(
                    "photo resolve: wikidata P18 fallback name=%r city=%r",
                    place_name,
                    city or None,
                )
                payload = wd
        except PlacesTransientError as exc:
            _note_transient(exc, what="wikidata")

    def _try_openverse() -> None:
        nonlocal payload, transient
        if payload.get("photo_data_url") or payload.get("photo_url"):
            return
        if openverse_lookup_in_backoff():
            transient = True
            logger.info(
                "photo resolve: openverse skipped (backoff) name=%r",
                place_name,
            )
            return
        try:
            ov = resolve_openverse_photo_payload(
                place_name,
                city=city,
                include_bytes=True,
            )
            if ov.get("photo_data_url") or ov.get("photo_url"):
                logger.info(
                    "photo resolve: openverse fallback name=%r city=%r",
                    place_name,
                    city or None,
                )
                payload = ov
        except PlacesTransientError as exc:
            _note_transient(exc, what="openverse")

    def _try_public_fallbacks() -> None:
        """Wikipedia → Wikidata P18 → Openverse (last resort; stricter quotas)."""
        _try_wikipedia()
        _try_wikidata()
        _try_openverse()

    def _try_enrich_then_google() -> None:
        nonlocal payload, owned, stored_photo_name, stored_place_id
        if payload.get("photo_data_url") or payload.get("photo_url"):
            return
        try:
            owned = _ensure_photo_refs(owned)
            stored_photo_name, stored_place_id = _google_refs(owned)
            _try_google_payload()
        except PlacesTransientError as exc:
            _note_transient(exc, what="enrich")

    # 1) Existing Google refs.
    _try_google_payload()

    # 2) While Places is in 429 backoff, skip Text Search and use public fallbacks.
    #    Otherwise enrich (Text Search) then public fallbacks.
    if places_lookup_in_backoff():
        _try_public_fallbacks()
    else:
        _try_enrich_then_google()
        _try_public_fallbacks()

    resolved_place_id = stored_place_id or (
        str(owned.get("place_id") or "").strip()
        if is_usable_google_place_id(
            str(owned.get("place_id") or "") or None,
            place_key=pk or None,
        )
        else None
    )

    if not payload.get("photo_data_url") and not payload.get("photo_url"):
        if prior_stable_url:
            # Re-resolve failed (quota / flaky wiki) — keep the durable Wikimedia URL.
            payload = resolve_cached_stable_photo_payload(
                prior_stable_url,
                places_photo_name=str(owned.get("places_photo_name") or "").strip()
                or None,
                include_bytes=True,
            )
        elif transient:
            # Do not durable-miss: rate limits / 5xx are temporary.
            raise ApiError(
                503,
                "Photo provider is temporarily unavailable; try again shortly",
                code="photo_temporarily_unavailable",
            )
        else:
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
