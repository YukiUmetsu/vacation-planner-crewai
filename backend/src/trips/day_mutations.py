"""Remove / reorder place and delete day.

Per ADR 005: takes ``table`` as an explicit arg and must never import
``trips.service.TripService``. May import ``trips.crud`` and ``trips.prompts``.
"""

from __future__ import annotations

from typing import Any

from db import repository as repo
from db.protocols import DynamoDBTable
from http_utils import ApiError, public_item

from trips.crud import _load_owned_bundle
from trips.day_status import status_after_day_edit
from trips.prompts import rebuild_prior_days_summary


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
    if trip.get("crew_job_kind") is not None:
        raise ApiError(
            409,
            "cannot edit places while a GenAI job is in progress",
            code="crew_job_in_progress",
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


def reorder_place(
    *,
    user_sub: str,
    trip_id: str,
    day_index: int,
    from_index: int,
    to_index: int,
    table: DynamoDBTable | None,
) -> dict[str, Any]:
    """Move one place within a day by list index and reindex order_in_day."""
    if day_index < 1:
        raise ApiError(400, "day_index must be >= 1", code="invalid_day_index")
    if from_index < 0 or to_index < 0:
        raise ApiError(400, "indices must be >= 0", code="invalid_place_index")

    trip, _route, days = _load_owned_bundle(user_sub=user_sub, trip_id=trip_id, table=table)
    if trip.get("planning_day_index") is not None:
        raise ApiError(
            409,
            "cannot edit places while planning is in progress",
            code="planning_in_progress",
        )
    if trip.get("crew_job_kind") is not None:
        raise ApiError(
            409,
            "cannot edit places while a GenAI job is in progress",
            code="crew_job_in_progress",
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
    n = len(existing)
    if from_index >= n or to_index >= n:
        raise ApiError(404, "place not found", code="not_found")
    if from_index == to_index:
        return {"day": public_item(day), "trip": public_item(trip)}

    moved = existing.pop(from_index)
    existing.insert(to_index, moved)
    updated_places: list[dict[str, Any]] = []
    for index, place in enumerate(existing):
        item = dict(place) if isinstance(place, dict) else {}
        item["order_in_day"] = index + 1
        updated_places.append(item)

    try:
        day_item = repo.replace_day_places(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            places=updated_places,
            expected_place_count=n,
            table=table,
        )
    except repo.ConcurrentModificationError as exc:
        raise ApiError(409, str(exc), code="conflict") from exc

    return {
        "day": public_item(day_item),
        "trip": public_item(trip),
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
    if trip.get("crew_job_kind") is not None:
        raise ApiError(
            409,
            "cannot delete a day while a GenAI job is in progress",
            code="crew_job_in_progress",
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
