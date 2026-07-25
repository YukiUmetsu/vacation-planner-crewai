"""Plan-next-day orchestration: claim, crew call, quality retries, persistence.

Per ADR 005: takes `table` / `runner` / `safety` / `enqueue_plan_day` as
explicit args and must never import `trips.service.TripService`. May import
`trips.crud` and `trips.city_route` (one-way — neither imports this module).
"""

from __future__ import annotations

import json
from typing import Any, Callable

from crews.runner import CrewRunner
from db import repository as repo
from db.protocols import DynamoDBTable
from http_utils import ApiError, client_facing_message, public_item
from crew_io.context_budget import inputs_char_len, slim_crew_inputs
from shared.dates import date_for_day_index, parse_iso_date
from planning_quality.day_balance import (
    day_balance_guidance,
    day_shape_hint,
    detect_food_crawl_mode,
    min_non_food_places_for,
    require_day_balance,
)
from planning_quality.dedupe import dedupe_places
from shared.energy import (
    clamp_energy_level,
    max_minutes_for_energy,
    target_place_count_for_energy,
)
from planning_quality.plan_day_retry import (
    MAX_PLAN_DAY_ATTEMPTS,
    apply_plan_day_retry_inputs,
    labels_to_ban_after_failure,
    merge_banned_labels,
    should_retry_plan_day,
)
from planning_quality.place_quality import (
    filter_quality_places,
    profile_visited_name_keys,
    require_meal_stops,
)
from crew_io.envelope import unwrap_crew_payload
from planning_quality.quality_policy import (
    enforce_hard_quality,
    merge_quality_reports,
    scrub_bff_resolved_tags,
)
from ops.plan_day_worker import (
    enqueue_plan_next_day_worker,
    plan_next_day_async_enabled,
)
from places.enrich import enrich_places
from user_profile.service import ProfileService
from safety.gate import SafetyGate
from ops.worker_observability import log_quality_metrics

from trips.city_route import _route_payload, overnight_city_for_day
from trips.crud import _load_owned_bundle, _require_trip, _json_safe
from trips.day_index import first_missing_day_index, resolve_plan_day_index
from trips.prompts import _meal_guidance, _merge_preferences, _profile_visited_keys


def _day_exists(
    *, user_sub: str, trip_id: str, day_index: int, table: DynamoDBTable | None
) -> bool:
    return (
        repo.get_day(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            table=table,
        )
        is not None
    )


def _cursors_from_existing_day(
    *,
    trip: dict[str, Any],
    day_item: dict[str, Any],
    next_index: int,
    fallback_visited: list[str],
    fallback_summary: str,
) -> tuple[list[str], str]:
    trip_visited = list(trip.get("visited_place_keys") or [])
    places = list(day_item.get("places") or [])
    new_keys = [str(p.get("place_key")) for p in places if p.get("place_key")]
    if new_keys:
        visited = trip_visited + [k for k in new_keys if k not in trip_visited]
    else:
        visited = fallback_visited
    theme = str(day_item.get("theme") or f"Day {next_index}")
    overnight = str(day_item.get("overnight_city") or "")
    prior = str(trip.get("prior_days_summary") or "").strip()
    line = f"Day {next_index}: {theme} @ {overnight}".strip()
    if line.endswith("@"):
        line = line[:-1].strip()
    summary = f"{prior}\n{line}".strip() if prior else line
    return visited, summary or fallback_summary


def _finalize_existing_planned_day(
    *,
    user_sub: str,
    trip_id: str,
    trip: dict[str, Any],
    day_index: int,
    ensure_claim: bool,
    table: DynamoDBTable | None,
) -> dict[str, Any] | None:
    """If DAY already exists, advance cursors / clear claim. Returns sync body or None."""
    existing = repo.get_day(
        user_sub=user_sub,
        trip_id=trip_id,
        day_index=day_index,
        table=table,
    )
    if existing is None:
        return None

    if ensure_claim and trip.get("planning_day_index") is None:
        try:
            trip = repo.claim_planning_in_progress(
                user_sub=user_sub,
                trip_id=trip_id,
                expected_next_day_index=day_index,
                table=table,
            )
        except repo.ConcurrentModificationError:
            trip = _require_trip(user_sub=user_sub, trip_id=trip_id, table=table)

    claimed = trip.get("planning_day_index")
    try:
        claimed_i = int(claimed) if claimed is not None else None
    except (TypeError, ValueError):
        claimed_i = None
    if claimed_i != day_index:
        # Cursor already advanced past this day — treat as done.
        if int(trip.get("next_day_index") or 0) > day_index:
            return {
                "async": False,
                "day": public_item(existing),
                "trip": public_item(trip),
            }
        return None

    day_count = int(trip["day_count"])
    next_day_index = day_index + 1
    new_status = "complete" if next_day_index > day_count else "planning"
    visited, summary = _cursors_from_existing_day(
        trip=trip,
        day_item=existing,
        next_index=day_index,
        fallback_visited=list(trip.get("visited_place_keys") or []),
        fallback_summary=str(trip.get("prior_days_summary") or ""),
    )
    try:
        repo.complete_planning_after_day_write(
            user_sub=user_sub,
            trip_id=trip_id,
            planned_day_index=day_index,
            next_day_index=next_day_index,
            visited_place_keys=visited,
            prior_days_summary=summary,
            new_status=new_status,
            table=table,
        )
    except repo.ConcurrentModificationError as exc:
        trip_out = _require_trip(user_sub=user_sub, trip_id=trip_id, table=table)
        if int(trip_out.get("next_day_index") or 0) > day_index:
            return {
                "async": False,
                "day": public_item(existing),
                "trip": public_item(trip_out),
            }
        raise ApiError(409, str(exc), code="conflict") from exc

    trip_out = _require_trip(user_sub=user_sub, trip_id=trip_id, table=table)
    return {
        "async": False,
        "day": public_item(existing),
        "trip": public_item(trip_out),
    }


def _run_plan_day_and_persist(
    *,
    user_sub: str,
    trip_id: str,
    trip: dict[str, Any],
    route: dict[str, Any] | None,
    next_index: int,
    async_claimed: bool,
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
    rollback_status: str = "planning",
) -> dict[str, Any]:
    day_count = int(trip["day_count"])
    start = parse_iso_date(str(trip["start_date"]), field="start_date")
    day_date = date_for_day_index(start, next_index)
    overnight = overnight_city_for_day(route, next_index, str(trip["destination"]))

    safety.check_text(str(trip.get("preferences") or ""), source="preferences")

    profile = ProfileService(table=table, safety=safety).get_profile(user_sub)
    energy_level = clamp_energy_level(profile.get("energy_level"))
    max_minutes = max_minutes_for_energy(energy_level)
    target_places = target_place_count_for_energy(energy_level)
    interests = [str(i) for i in (profile.get("interests") or []) if str(i).strip()]
    include_breakfast = bool(profile.get("suggest_include_breakfast"))
    merged_prefs = _merge_preferences(
        str(trip.get("preferences") or ""),
        str(profile.get("preferences") or ""),
        interests,
    )
    food_crawl_mode = detect_food_crawl_mode(merged_prefs, interests)
    min_non_food = min_non_food_places_for(food_crawl_mode=food_crawl_mode)
    meal_line = _meal_guidance(include_breakfast=include_breakfast)
    balance_line = day_balance_guidance(
        food_crawl_mode=food_crawl_mode,
        min_non_food_places=min_non_food,
    )
    # Prepend (not append): slim_crew_inputs truncates preferences from the
    # end when over budget, so meal + day-balance rules must stay at the front.
    for line in (meal_line, balance_line):
        if line not in merged_prefs:
            merged_prefs = (
                f"{line} | {merged_prefs}".strip(" |")
                if merged_prefs
                else line
            )
    safety.check_text(merged_prefs, source="preferences")

    visited = list(trip.get("visited_place_keys") or [])
    for key in _profile_visited_keys(list(profile.get("visited_places") or [])):
        if key not in visited:
            visited.append(key)

    route_for_crew = _route_payload(route) if route else {}
    raw_inputs = {
        "origin": trip["origin"],
        "destination": trip["destination"],
        "destination_type": trip["destination_type"],
        "day_index": str(next_index),
        "date": day_date.isoformat(),
        "overnight_city": overnight,
        "preferences": merged_prefs,
        "include_breakfast": "true" if include_breakfast else "false",
        "food_crawl_mode": "true" if food_crawl_mode else "false",
        "min_non_food_places": str(min_non_food),
        "day_shape_hint": day_shape_hint(
            food_crawl_mode=food_crawl_mode,
            target_place_count=target_places,
        ),
        "energy_level": str(energy_level),
        "max_comfortable_minutes": str(max_minutes),
        "target_place_count": str(target_places),
        "interests": ", ".join(interests),
        "already_visited": ",".join(visited),
        "prior_days_summary": trip.get("prior_days_summary") or "",
        "city_route_json": (
            json.dumps(_json_safe(route_for_crew)) if route_for_crew else ""
        ),
    }
    before_chars = inputs_char_len(raw_inputs)
    base_inputs = slim_crew_inputs(
        raw_inputs,
        overnight_city=overnight,
        day_index=next_index,
    )
    context_was_slimmed = inputs_char_len(base_inputs) < before_chars
    if context_was_slimmed:
        base_inputs = {**base_inputs, "__context_was_slimmed": "true"}

    day_data: dict[str, Any] | None = None
    crew_quality: Any = None
    invocation: dict[str, Any] | None = None
    filtered: list[dict[str, Any]] = []
    energy_soft_tags: list[str] = []
    banned: list[str] = []
    last_quality_error: ApiError | None = None
    profile_visited_names = profile_visited_name_keys(
        list(profile.get("visited_places") or [])
    )

    for attempt in range(MAX_PLAN_DAY_ATTEMPTS):
        inputs = apply_plan_day_retry_inputs(
            base_inputs,
            attempt=attempt,
            failure_code=(
                str(last_quality_error.code)
                if last_quality_error is not None
                else None
            ),
            banned_places=banned,
        )
        raw_day = runner.plan_day(inputs)
        day_data, crew_quality, invocation = unwrap_crew_payload(raw_day)
        if invocation is not None:
            invocation = {
                **invocation,
                "context_was_slimmed": bool(
                    invocation.get("context_was_slimmed")
                )
                or context_was_slimmed,
                "plan_day_attempt": attempt + 1,
            }
        places = list((day_data or {}).get("places") or [])
        filtered = dedupe_places(places, visited)
        if len(filtered) < 1:
            last_quality_error = ApiError(
                422,
                "all suggested places were already visited",
                code="dedupe_empty",
            )
            banned = merge_banned_labels(
                banned,
                labels_to_ban_after_failure(
                    code="dedupe_empty",
                    places=places,
                    plan_date=day_date,
                    profile_visited_names=profile_visited_names,
                ),
            )
            if should_retry_plan_day(
                code=last_quality_error.code, attempt=attempt
            ):
                continue
            log_quality_metrics(
                trip_id=trip_id,
                day_index=next_index,
                quality=merge_quality_reports(
                    crew_quality, {"failure_tags": ["duplicate_place"]}
                ),
                invocation=invocation,
                guardrail_code="dedupe_empty",
                places_count=0,
            )
            raise last_quality_error

        filtered = enrich_places(
            filtered,
            overnight_city=overnight,
        )
        try:
            filtered, energy_soft_tags = filter_quality_places(
                filtered,
                plan_date=day_date,
                max_comfortable_minutes=max_minutes,
                profile_visited_names=profile_visited_names,
                include_breakfast=include_breakfast,
                food_crawl_mode=food_crawl_mode,
            )
            require_meal_stops(filtered, include_breakfast=include_breakfast)
            require_day_balance(
                filtered,
                food_crawl_mode=food_crawl_mode,
                min_non_food_places=min_non_food,
            )
            last_quality_error = None
            break
        except ApiError as exc:
            last_quality_error = exc
            banned = merge_banned_labels(
                banned,
                labels_to_ban_after_failure(
                    code=exc.code,
                    places=filtered,
                    plan_date=day_date,
                    profile_visited_names=profile_visited_names,
                ),
            )
            if should_retry_plan_day(code=exc.code, attempt=attempt):
                continue
            tag = {
                "quality_empty": "closed_place",
                "missing_meals": "missing_meals",
                "food_only_day": "food_only_day",
            }.get(str(exc.code or ""), "")
            log_quality_metrics(
                trip_id=trip_id,
                day_index=next_index,
                quality=merge_quality_reports(
                    crew_quality,
                    {"failure_tags": [tag]} if tag else crew_quality,
                ),
                invocation=invocation,
                guardrail_code=exc.code,
                places_count=len(filtered) if filtered else 0,
            )
            raise

    if last_quality_error is not None:
        raise last_quality_error
    if day_data is None:
        raise ApiError(500, "day plan missing after retries", code="internal_error")

    merged_quality = merge_quality_reports(
        scrub_bff_resolved_tags(crew_quality),
        {"failure_tags": energy_soft_tags} if energy_soft_tags else None,
    )
    try:
        enforce_hard_quality(merged_quality)
    except ApiError as exc:
        log_quality_metrics(
            trip_id=trip_id,
            day_index=next_index,
            quality=merged_quality,
            invocation=invocation,
            guardrail_code=exc.code,
            places_count=len(filtered),
        )
        raise
    log_quality_metrics(
        trip_id=trip_id,
        day_index=next_index,
        quality=merged_quality,
        invocation=invocation,
        places_count=len(filtered),
    )
    day_data = {
        **day_data,
        "day_index": next_index,
        "date": day_date.isoformat(),
        "overnight_city": overnight,
        "places": filtered,
    }

    trip_visited = list(trip.get("visited_place_keys") or [])
    new_keys = [str(p.get("place_key")) for p in filtered if p.get("place_key")]
    updated_visited = trip_visited + [k for k in new_keys if k not in trip_visited]
    theme = str(day_data.get("theme") or f"Day {next_index}")
    prior = str(trip.get("prior_days_summary") or "").strip()
    line = f"Day {next_index}: {theme} @ {overnight}"
    prior_summary = f"{prior}\n{line}".strip() if prior else line

    next_day_index = next_index + 1
    new_status = "complete" if next_day_index > day_count else "planning"

    try:
        if async_claimed:
            day_item = _persist_async_planned_day(
                user_sub=user_sub,
                trip_id=trip_id,
                trip=trip,
                day_data=day_data,
                next_index=next_index,
                next_day_index=next_day_index,
                updated_visited=updated_visited,
                prior_summary=prior_summary,
                new_status=new_status,
                table=table,
            )
        else:
            day_item = repo.persist_planned_day(
                user_sub=user_sub,
                trip_id=trip_id,
                day=day_data,
                expected_next_day_index=next_index,
                visited_place_keys=updated_visited,
                prior_days_summary=prior_summary,
                new_status=new_status,
                rollback_status=rollback_status,
                table=table,
            )
    except repo.ConcurrentModificationError as exc:
        raise ApiError(409, str(exc), code="conflict") from exc

    trip_out = _require_trip(user_sub=user_sub, trip_id=trip_id, table=table)
    return {
        "async": False,
        "day": public_item(day_item),
        "trip": public_item(trip_out),
    }


def _persist_async_planned_day(
    *,
    user_sub: str,
    trip_id: str,
    trip: dict[str, Any],
    day_data: dict[str, Any],
    next_index: int,
    next_day_index: int,
    updated_visited: list[str],
    prior_summary: str,
    new_status: str,
    table: DynamoDBTable | None,
) -> dict[str, Any]:
    """Put DAY then clear claim; idempotent if DAY already exists."""
    live = repo.get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=table)
    if not live:
        raise ApiError(404, "trip not found", code="not_found")
    if str(live.get("status") or "") == "deleting":
        raise ApiError(409, "trip is being deleted", code="trip_deleting")
    try:
        claimed_i = int(live.get("planning_day_index"))
    except (TypeError, ValueError):
        claimed_i = None
    if claimed_i != next_index:
        raise ApiError(
            409,
            "planning claim lost before day write",
            code="claim_mismatch",
        )

    existing = repo.get_day(
        user_sub=user_sub,
        trip_id=trip_id,
        day_index=next_index,
        table=table,
    )
    if existing is not None:
        day_item = existing
        visited, summary = _cursors_from_existing_day(
            trip=live,
            day_item=existing,
            next_index=next_index,
            fallback_visited=updated_visited,
            fallback_summary=prior_summary,
        )
    else:
        try:
            day_item = repo.put_day_if_absent(
                user_sub=user_sub,
                trip_id=trip_id,
                day=day_data,
                table=table,
            )
            visited, summary = updated_visited, prior_summary
        except repo.ConcurrentModificationError:
            # Another writer finished the Put; complete the claim from that DAY.
            day_item = repo.get_day(
                user_sub=user_sub,
                trip_id=trip_id,
                day_index=next_index,
                table=table,
            )
            if day_item is None:
                raise
            visited, summary = _cursors_from_existing_day(
                trip=live,
                day_item=day_item,
                next_index=next_index,
                fallback_visited=updated_visited,
                fallback_summary=prior_summary,
            )

    repo.complete_planning_after_day_write(
        user_sub=user_sub,
        trip_id=trip_id,
        planned_day_index=next_index,
        next_day_index=next_day_index,
        visited_place_keys=visited,
        prior_days_summary=summary,
        new_status=new_status,
        table=table,
    )
    return day_item


def plan_next_day_sync(
    *,
    user_sub: str,
    trip_id: str,
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
) -> dict[str, Any]:
    trip, route, days = _load_owned_bundle(user_sub=user_sub, trip_id=trip_id, table=table)
    status = trip.get("status")
    if status not in {"routing_confirmed", "planning", "failed"}:
        raise ApiError(
            409, f"cannot plan day from status={status!r}", code="bad_status"
        )

    if trip["destination_type"] != "city":
        if not route or route.get("status") != "confirmed":
            raise ApiError(409, "confirmed city route required", code="route_required")

    next_index = resolve_plan_day_index(trip=trip, days=days)
    stored_next = int(trip.get("next_day_index") or 1)
    if stored_next != next_index:
        trip = repo.update_trip(
            user_sub=user_sub,
            trip_id=trip_id,
            updates={"next_day_index": next_index},
            table=table,
        )

    return _run_plan_day_and_persist(
        user_sub=user_sub,
        trip_id=trip_id,
        trip=trip,
        route=route,
        next_index=next_index,
        async_claimed=False,
        table=table,
        runner=runner,
        safety=safety,
        rollback_status=str(status),
    )


def start_plan_next_day(
    *,
    user_sub: str,
    trip_id: str,
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
    enqueue_plan_day: Callable[[str, str, int], None] | None,
) -> dict[str, Any]:
    """Claim planning slot and enqueue worker; returns async response shape."""
    trip, route, days = _load_owned_bundle(user_sub=user_sub, trip_id=trip_id, table=table)
    status = trip.get("status")
    if status not in {"routing_confirmed", "planning", "failed"}:
        raise ApiError(
            409, f"cannot plan day from status={status!r}", code="bad_status"
        )

    if trip["destination_type"] != "city":
        if not route or route.get("status") != "confirmed":
            raise ApiError(409, "confirmed city route required", code="route_required")

    # Finish an in-flight claim before filling gaps (orphan DAY after worker Put).
    claimed_raw = trip.get("planning_day_index")
    if claimed_raw is not None:
        try:
            claimed_i = int(claimed_raw)
        except (TypeError, ValueError):
            claimed_i = None
        if claimed_i is not None and claimed_i >= 1:
            recovered = _finalize_existing_planned_day(
                user_sub=user_sub,
                trip_id=trip_id,
                trip=trip,
                day_index=claimed_i,
                ensure_claim=False,
                table=table,
            )
            if recovered is not None:
                return recovered
            # No DAY yet for the claim — drop only if stuck long enough.
            if repo.clear_stale_planning_claim(
                user_sub=user_sub, trip_id=trip_id, table=table
            ):
                trip = _require_trip(user_sub=user_sub, trip_id=trip_id, table=table)
            else:
                raise ApiError(
                    409,
                    "a day is already being planned for this trip",
                    code="conflict",
                )

    next_index = resolve_plan_day_index(trip=trip, days=days)
    stored_next = int(trip.get("next_day_index") or 1)
    if stored_next != next_index:
        # Heal skipped cursor (e.g. claim advanced but DAY put failed).
        trip = repo.update_trip(
            user_sub=user_sub,
            trip_id=trip_id,
            updates={"next_day_index": next_index},
            table=table,
        )

    # DAY already present (worker died after Put) — finish cursor without re-crew.
    recovered = _finalize_existing_planned_day(
        user_sub=user_sub,
        trip_id=trip_id,
        trip=trip,
        day_index=next_index,
        ensure_claim=True,
        table=table,
    )
    if recovered is not None:
        return recovered

    try:
        claimed = repo.claim_planning_in_progress(
            user_sub=user_sub,
            trip_id=trip_id,
            expected_next_day_index=next_index,
            table=table,
        )
    except repo.ConcurrentModificationError as exc:
        trip = _require_trip(user_sub=user_sub, trip_id=trip_id, table=table)
        recovered = _finalize_existing_planned_day(
            user_sub=user_sub,
            trip_id=trip_id,
            trip=trip,
            day_index=next_index,
            ensure_claim=False,
            table=table,
        )
        if recovered is not None:
            return recovered
        raise ApiError(409, str(exc), code="conflict") from exc

    enqueue = enqueue_plan_day or enqueue_plan_next_day_worker
    try:
        enqueue(user_sub, trip_id, next_index)
    except Exception as exc:
        repo.fail_planning_in_progress(
            user_sub=user_sub,
            trip_id=trip_id,
            planned_day_index=next_index,
            error_message=client_facing_message(
                status_code=502,
                code="enqueue_failed",
                detail=f"failed to start planner: {type(exc).__name__}",
            ),
            table=table,
        )
        raise ApiError(
            502,
            client_facing_message(
                status_code=502,
                code="enqueue_failed",
                detail="failed to start async plan-next-day worker",
            ),
            code="enqueue_failed",
        ) from exc

    return {
        "async": True,
        "trip": public_item(claimed),
        "planning_day_index": next_index,
    }


def execute_plan_next_day(
    *,
    user_sub: str,
    trip_id: str,
    day_index: int,
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
) -> dict[str, Any]:
    """Worker path: run crew + enrich + persist for an already-claimed day."""
    trip, route, _days = _load_owned_bundle(user_sub=user_sub, trip_id=trip_id, table=table)
    if str(trip.get("status") or "") == "deleting":
        raise ApiError(
            409,
            "trip is being deleted",
            code="trip_deleting",
        )
    claimed = trip.get("planning_day_index")
    try:
        claimed_i = int(claimed) if claimed is not None else None
    except (TypeError, ValueError):
        claimed_i = None
    if claimed_i != day_index:
        raise ApiError(
            409,
            f"planning claim mismatch (expected {day_index}, got {claimed!r})",
            code="claim_mismatch",
        )

    next_index = int(trip.get("next_day_index") or 1)
    if next_index != day_index:
        raise ApiError(
            409,
            "next_day_index no longer matches claimed day",
            code="claim_mismatch",
        )

    recovered = _finalize_existing_planned_day(
        user_sub=user_sub,
        trip_id=trip_id,
        trip=trip,
        day_index=day_index,
        ensure_claim=False,
        table=table,
    )
    if recovered is not None:
        return recovered

    try:
        return _run_plan_day_and_persist(
            user_sub=user_sub,
            trip_id=trip_id,
            trip=trip,
            route=route,
            next_index=next_index,
            async_claimed=True,
            table=table,
            runner=runner,
            safety=safety,
        )
    except ApiError as exc:
        # Retryable AgentCore transport errors: keep claim so Event retries run.
        if (
            not exc.retryable
            and not _day_exists(user_sub=user_sub, trip_id=trip_id, day_index=day_index, table=table)
        ):
            repo.fail_planning_in_progress(
                user_sub=user_sub,
                trip_id=trip_id,
                planned_day_index=day_index,
                error_message=client_facing_message(
                    status_code=exc.status_code,
                    code=exc.code,
                    detail=exc.message,
                ),
                table=table,
            )
        raise
    except Exception as exc:
        if not _day_exists(user_sub=user_sub, trip_id=trip_id, day_index=day_index, table=table):
            repo.fail_planning_in_progress(
                user_sub=user_sub,
                trip_id=trip_id,
                planned_day_index=day_index,
                error_message=client_facing_message(
                    status_code=500,
                    code="internal_error",
                    detail=f"{type(exc).__name__}: {exc}",
                ),
                table=table,
            )
        raise


def plan_next_day(
    *,
    user_sub: str,
    trip_id: str,
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
    enqueue_plan_day: Callable[[str, str, int], None] | None,
) -> dict[str, Any]:
    """Plan the next day — sync 200 body, or async 202 body when agentcore."""
    if plan_next_day_async_enabled():
        return start_plan_next_day(
            user_sub=user_sub,
            trip_id=trip_id,
            table=table,
            runner=runner,
            safety=safety,
            enqueue_plan_day=enqueue_plan_day,
        )
    return plan_next_day_sync(
        user_sub=user_sub,
        trip_id=trip_id,
        table=table,
        runner=runner,
        safety=safety,
    )
