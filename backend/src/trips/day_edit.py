"""Day-plan edits: suggest one place, remove a place, delete a whole day.

Per ADR 005: takes `table` / `runner` / `safety` as explicit args and must
never import `trips.service.TripService`. May import `trips.crud`,
`trips.day_index`, and `trips.prompts` (one-way — none of those import this
module). Does not import `trips.plan_day` (avoids pulling the plan graph).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from crews.runner import CrewRunner
from db import repository as repo
from db.protocols import DynamoDBTable
from http_utils import ApiError, client_facing_message, public_item
from crew_io.context_budget import slim_crew_inputs
from shared.dates import date_for_day_index, parse_iso_date
from planning_quality.day_balance import (
    day_balance_guidance,
    detect_food_crawl_mode,
    min_non_food_places_for,
    prefer_non_food_suggestion,
    require_suggested_place_balance,
)
from shared.energy import MAX_PLACES_PER_DAY, clamp_energy_level, max_minutes_for_energy
from planning_quality.place_quality import (
    day_total_minutes,
    profile_visited_name_keys,
    validate_suggested_place,
)
from crew_io.envelope import unwrap_crew_payload
from ops.worker_observability import log_quality_metrics
from places.client import PlacesTransientError
from places.enrich import enrich_place
from user_profile.service import ProfileService
from safety.gate import SafetyGate

from trips.crud import _json_safe, _load_owned_bundle, _require_trip
from trips.day_index import first_missing_day_index
from trips.prompts import _merge_preferences, _profile_visited_keys, rebuild_prior_days_summary

logger = logging.getLogger(__name__)


def status_after_day_edit(
    *,
    remaining_days: list[dict[str, Any]],
    day_count: int,
    previous_status: str,
) -> tuple[int, str]:
    """Return (next_day_index, status) after a day was removed or emptied."""
    gap = first_missing_day_index(remaining_days, day_count)
    if gap is None:
        return day_count + 1, "complete"
    if not remaining_days:
        # Route is still confirmed; traveler can plan again from day 1.
        if previous_status in {"planning", "complete", "failed"}:
            return 1, "routing_confirmed"
        return 1, previous_status or "routing_confirmed"
    return gap, "planning"


def suggest_place(
    *,
    user_sub: str,
    trip_id: str,
    day_index: int,
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
    email: str | None = None,
) -> dict[str, Any]:
    """Research and append one place to an existing planned day."""
    from limits.genai import consume_genai_action

    if day_index < 1:
        raise ApiError(400, "day_index must be >= 1", code="invalid_day_index")

    trip = _require_trip(user_sub=user_sub, trip_id=trip_id, table=table)
    day_count = int(trip.get("day_count") or 0)
    if day_count and day_index > day_count:
        raise ApiError(
            400,
            f"day_index {day_index} is outside trip window 1..{day_count}",
            code="invalid_day_index",
        )
    day = repo.get_day(
        user_sub=user_sub,
        trip_id=trip_id,
        day_index=day_index,
        table=table,
    )
    if not day:
        raise ApiError(404, "day not found", code="not_found")

    existing = list(day.get("places") or [])
    if len(existing) >= MAX_PLACES_PER_DAY:
        raise ApiError(
            422,
            f"day already has the maximum of {MAX_PLACES_PER_DAY} places",
            code="day_full",
        )

    profile = ProfileService(table=table, safety=safety).get_profile(
        user_sub, email=email
    )

    start = parse_iso_date(str(trip["start_date"]), field="start_date")
    raw_date = str(day.get("date") or "").strip()
    if raw_date:
        day_date = parse_iso_date(raw_date[:10], field="date")
    else:
        day_date = date_for_day_index(start, day_index)
    overnight = str(day.get("overnight_city") or trip["destination"])

    energy_level = clamp_energy_level(profile.get("energy_level"))
    max_minutes = max_minutes_for_energy(energy_level)
    interests = [str(i) for i in (profile.get("interests") or []) if str(i).strip()]
    merged_prefs = _merge_preferences(
        str(trip.get("preferences") or ""),
        str(profile.get("preferences") or ""),
        interests,
    )
    food_crawl_mode = detect_food_crawl_mode(merged_prefs, interests)
    min_non_food = min_non_food_places_for(food_crawl_mode=food_crawl_mode)
    prefer_non_food = prefer_non_food_suggestion(
        existing, food_crawl_mode=food_crawl_mode
    )
    balance_line = day_balance_guidance(
        food_crawl_mode=food_crawl_mode,
        min_non_food_places=min_non_food,
    )
    if prefer_non_food:
        balance_line = (
            f"{balance_line} Prefer a non-food Place this round "
            "(museum, park, shrine, shopping, cultural POI) — the day still "
            "has no non-food stop."
        )
    if balance_line not in merged_prefs:
        merged_prefs = (
            f"{balance_line} | {merged_prefs}".strip(" |")
            if merged_prefs
            else balance_line
        )
    # Pre-crew gate: safety rejection must not consume GenAI quota.
    safety.check_text(merged_prefs, source="preferences")
    consume_genai_action(
        user_sub=user_sub, profile=profile, email=email, table=table
    )

    current_total = day_total_minutes(existing)
    remaining = max_minutes - current_total

    visited = list(trip.get("visited_place_keys") or [])
    for key in _profile_visited_keys(list(profile.get("visited_places") or [])):
        if key not in visited:
            visited.append(key)
    for place in existing:
        key = str(place.get("place_key") or "").strip()
        if key and key not in visited:
            visited.append(key)

    slim_current = [
        {
            "name": p.get("name"),
            "place_key": p.get("place_key"),
            "category": p.get("category"),
            "estimated_minutes": p.get("estimated_minutes"),
        }
        for p in existing
    ]
    inputs = slim_crew_inputs(
        {
            "overnight_city": overnight,
            "day_index": str(day_index),
            "date": day_date.isoformat(),
            "preferences": merged_prefs,
            "interests": ", ".join(interests),
            "food_crawl_mode": "true" if food_crawl_mode else "false",
            "prefer_non_food": "true" if prefer_non_food else "false",
            "min_non_food_places": str(min_non_food),
            "energy_level": str(energy_level),
            "remaining_minutes": str(remaining),
            "already_visited": ",".join(visited),
            "current_places_json": json.dumps(_json_safe(slim_current)),
            "next_order_in_day": str(len(existing) + 1),
        },
        overnight_city=overnight,
        day_index=day_index,
    )
    raw = runner.suggest_place(inputs)
    if (
        isinstance(raw, dict)
        and "error" in raw
        and "code" in raw
        and "place_key" not in raw
        and "result" not in raw
    ):
        code = str(raw.get("code") or "crew_failed")
        status = 400 if code in {"invalid_payload", "invalid_crew"} else 502
        detail = str(raw.get("error") or "suggest_place failed")
        raise ApiError(
            status,
            client_facing_message(status_code=status, code=code, detail=detail),
            code=code,
        )
    unwrapped, _, _ = unwrap_crew_payload(raw)
    candidate = (
        unwrapped.get("place")
        if isinstance(unwrapped.get("place"), dict)
        else unwrapped
    )
    if not isinstance(candidate, dict):
        raise ApiError(422, "crew did not return a place", code="invalid_place")

    try:
        candidate = enrich_place(
            candidate,
            overnight_city=overnight,
            destination=str(trip.get("destination") or ""),
        )
    except PlacesTransientError as exc:
        # Soft-fail like pre-rate-limit behavior — still return the crew place.
        logger.warning(
            "suggest enrich rate-limited trip=%s day=%s: %s",
            trip_id,
            day_index,
            exc,
        )
    validated, energy_soft_tags = validate_suggested_place(
        candidate,
        existing_places=existing,
        plan_date=day_date,
        max_comfortable_minutes=max_minutes,
        already_visited_keys=set(visited),
        profile_visited_names=profile_visited_name_keys(
            list(profile.get("visited_places") or [])
        ),
    )
    require_suggested_place_balance(
        validated,
        existing,
        food_crawl_mode=food_crawl_mode,
    )
    if energy_soft_tags:
        log_quality_metrics(
            trip_id=trip_id,
            day_index=day_index,
            quality={"passes_relevance": True, "failure_tags": energy_soft_tags},
            invocation=None,
            places_count=len(existing) + 1,
        )
    updated_places = [*existing, validated]
    place_key = str(validated.get("place_key") or "")
    trip_visited = list(trip.get("visited_place_keys") or [])
    try:
        day_item, trip = repo.persist_suggested_place(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            places=updated_places,
            expected_place_count=len(existing),
            place_key=place_key,
            previous_visited_keys=trip_visited,
            table=table,
        )
    except repo.ConcurrentModificationError as exc:
        raise ApiError(409, str(exc), code="conflict") from exc
    except repo.PersistenceError as exc:
        raise ApiError(502, str(exc), code="persistence_error") from exc

    return {
        "place": validated,
        "day": public_item(day_item),
        "trip": public_item(trip),
    }


def remove_place(
    *,
    user_sub: str,
    trip_id: str,
    day_index: int,
    place_index: int,
    table: DynamoDBTable | None,
) -> dict[str, Any]:
    """Remove one place from a day by list index and reindex order_in_day."""
    if day_index < 1:
        raise ApiError(400, "day_index must be >= 1", code="invalid_day_index")
    if place_index < 0:
        raise ApiError(400, "place_index must be >= 0", code="invalid_place_index")

    trip, _route, days = _load_owned_bundle(user_sub=user_sub, trip_id=trip_id, table=table)
    if trip.get("planning_day_index") is not None:
        raise ApiError(
            409,
            "cannot edit places while planning is in progress",
            code="planning_in_progress",
        )
    if str(trip.get("status") or "") == "deleting":
        raise ApiError(409, "trip is being deleted", code="trip_deleting")

    day = next(
        (d for d in days if int(d.get("day_index") or 0) == day_index),
        None,
    )
    if not day:
        raise ApiError(404, "day not found", code="not_found")

    existing = list(day.get("places") or [])
    if place_index >= len(existing):
        raise ApiError(404, "place not found", code="not_found")

    removed = existing[place_index]
    removed_key = (
        str(removed.get("place_key") or "").strip()
        if isinstance(removed, dict)
        else ""
    )

    updated_places: list[dict[str, Any]] = []
    for index, place in enumerate(existing):
        if index == place_index:
            continue
        item = dict(place) if isinstance(place, dict) else {}
        item["order_in_day"] = len(updated_places) + 1
        updated_places.append(item)

    try:
        day_item = repo.replace_day_places(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            places=updated_places,
            expected_place_count=len(existing),
            table=table,
        )
    except repo.ConcurrentModificationError as exc:
        raise ApiError(409, str(exc), code="conflict") from exc

    remaining = [
        day_item if int(d.get("day_index") or 0) == day_index else d for d in days
    ]
    still_used = False
    if removed_key:
        for other in remaining:
            for place in other.get("places") or []:
                if not isinstance(place, dict):
                    continue
                if str(place.get("place_key") or "").strip() == removed_key:
                    still_used = True
                    break
            if still_used:
                break

    trip_out = trip
    if removed_key and not still_used:
        try:
            trip_out = repo.prune_visited_place_keys(
                user_sub=user_sub,
                trip_id=trip_id,
                keys_to_remove={removed_key},
                table=table,
            )
        except repo.ConcurrentModificationError:
            # Place already removed; visited may be slightly stale — do not 409.
            trip_out = (
                repo.get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=table)
                or trip
            )
    else:
        trip_out = (
            repo.get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=table)
            or trip
        )

    return {
        "day": public_item(day_item),
        "trip": public_item(trip_out),
    }


def delete_day(
    *,
    user_sub: str,
    trip_id: str,
    day_index: int,
    table: DynamoDBTable | None,
) -> dict[str, Any]:
    """Delete an entire day plan and rewind planning cursors for gaps."""
    if day_index < 1:
        raise ApiError(400, "day_index must be >= 1", code="invalid_day_index")

    trip, _route, days = _load_owned_bundle(user_sub=user_sub, trip_id=trip_id, table=table)
    if not any(int(d.get("day_index") or 0) == day_index for d in days):
        raise ApiError(404, "day not found", code="not_found")

    if trip.get("planning_day_index") is not None:
        raise ApiError(
            409,
            "cannot delete a day while planning is in progress",
            code="planning_in_progress",
        )
    if str(trip.get("status") or "") == "deleting":
        raise ApiError(409, "trip is being deleted", code="trip_deleting")

    deleted = next(
        (d for d in days if int(d.get("day_index") or 0) == day_index),
        None,
    )
    deleted_keys = {
        str(p.get("place_key") or "").strip()
        for p in (deleted.get("places") or [] if deleted else [])
        if isinstance(p, dict) and str(p.get("place_key") or "").strip()
    }

    remaining = [d for d in days if int(d.get("day_index") or 0) != day_index]
    still_used = {
        str(p.get("place_key") or "").strip()
        for d in remaining
        for p in (d.get("places") or [])
        if isinstance(p, dict) and str(p.get("place_key") or "").strip()
    }
    keys_to_prune = deleted_keys - still_used

    day_count = int(trip.get("day_count") or 0)
    next_day_index, new_status = status_after_day_edit(
        remaining_days=remaining,
        day_count=day_count,
        previous_status=str(trip.get("status") or ""),
    )
    prior_summary = rebuild_prior_days_summary(remaining)

    # Cursor update first (fails if a claim appears) — then delete the DAY row.
    try:
        trip = repo.apply_itinerary_edit(
            user_sub=user_sub,
            trip_id=trip_id,
            next_day_index=next_day_index,
            status=new_status,
            prior_days_summary=prior_summary,
            table=table,
        )
    except repo.ConcurrentModificationError as exc:
        raise ApiError(409, str(exc), code="conflict") from exc

    if not repo.delete_day(
        user_sub=user_sub,
        trip_id=trip_id,
        day_index=day_index,
        table=table,
    ):
        # Cursors already reflect the gap; treat as idempotent success.
        pass

    if keys_to_prune:
        try:
            trip = repo.prune_visited_place_keys(
                user_sub=user_sub,
                trip_id=trip_id,
                keys_to_remove=keys_to_prune,
                table=table,
            )
        except repo.ConcurrentModificationError:
            trip = (
                repo.get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=table)
                or trip
            )

    return {
        "deleted_day_index": day_index,
        "trip": public_item(trip),
        "days": [public_item(d) for d in remaining],
    }
