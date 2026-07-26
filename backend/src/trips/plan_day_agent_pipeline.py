"""Plan-next-day *agent pipeline*: crew → quality gates → Dynamo persist.

This is the heavy lifting once a day slot is claimed (or sync path is ready):

1. Build slimmed crew inputs (prefs, visited, prior_days_summary, …)
2. Call the day_plan crew (with quality retries)
3. Enrich / dedupe / meal & day-balance checks
4. Write the DAY row and advance visited / prior-day cursors

Called only from ``trips.plan_day_jobs``. Takes ``table`` / ``runner`` /
``safety`` as explicit args — never imports ``trips.service.TripService``
(ADR 005).
"""

from __future__ import annotations

import json
import time
from typing import Any

from crews.runner import CrewRunner
from db import repository as repo
from db.protocols import DynamoDBTable
from http_utils import ApiError, public_item
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
from places.enrich import enrich_places
from user_profile.service import ProfileService
from safety.gate import SafetyGate
from ops.worker_observability import log_plan_day_retry, log_quality_metrics

from trips.city_route import _route_payload, overnight_city_for_day
from trips.crud import _require_trip, _json_safe
from trips.prompts import (
    _meal_guidance,
    _merge_preferences,
    _profile_visited_keys,
    append_prior_day_summary_line,
    prior_day_summary_line,
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
    line = prior_day_summary_line(
        day_index=next_index,
        theme=theme,
        overnight_city=overnight,
        places=places,
    )
    summary = append_prior_day_summary_line(prior, line)
    return visited, summary or fallback_summary


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
    email: str | None = None,
) -> dict[str, Any]:
    day_count = int(trip["day_count"])
    start = parse_iso_date(str(trip["start_date"]), field="start_date")
    day_date = date_for_day_index(start, next_index)
    overnight = overnight_city_for_day(route, next_index, str(trip["destination"]))

    safety.check_text(str(trip.get("preferences") or ""), source="preferences")

    profile = ProfileService(table=table, safety=safety).get_profile(
        user_sub, email=email
    )
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

    # Sync path only: charge after pre-crew safety. Async already charged at claim.
    if not async_claimed:
        from limits.genai import consume_genai_action

        consume_genai_action(
            user_sub=user_sub, profile=profile, email=email, table=table
        )

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

    def _note_dedupe_empty(places_for_ban: list[dict[str, Any]]) -> None:
        nonlocal last_quality_error, banned
        last_quality_error = ApiError(
            422,
            "all suggested places were already visited",
            code="dedupe_empty",
        )
        banned = merge_banned_labels(
            banned,
            labels_to_ban_after_failure(
                code="dedupe_empty",
                places=places_for_ban,
                plan_date=day_date,
                profile_visited_names=profile_visited_names,
            ),
        )

    def _will_retry_plan_day(
        *, code: str | None, attempt_idx: int, places_count: int
    ) -> bool:
        """Log RETRY_METRIC and return True when another crew attempt will run."""
        if not should_retry_plan_day(code=code, attempt=attempt_idx):
            return False
        log_plan_day_retry(
            trip_id=trip_id,
            day_index=next_index,
            attempt=attempt_idx + 1,
            failure_code=str(code or "unknown"),
            invocation=invocation,
            places_count=places_count,
        )
        return True

    def _raise_dedupe_empty_terminal() -> None:
        err = last_quality_error
        if err is None:
            raise ApiError(
                422,
                "all suggested places were already visited",
                code="dedupe_empty",
            )
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
        raise err

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
        started = time.perf_counter()
        raw_day = runner.plan_day(inputs)
        bff_latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        day_data, crew_quality, invocation = unwrap_crew_payload(raw_day)
        if invocation is None:
            invocation = {}
        invocation = {
            **invocation,
            "context_was_slimmed": bool(invocation.get("context_was_slimmed"))
            or context_was_slimmed,
            "plan_day_attempt": attempt + 1,
            # BFF wall clock includes AgentCore RTT; agent may also set latency_ms.
            "latency_ms": bff_latency_ms,
        }
        places = list((day_data or {}).get("places") or [])
        filtered = dedupe_places(places, visited)
        if len(filtered) < 1:
            _note_dedupe_empty(places)
            if _will_retry_plan_day(
                code="dedupe_empty", attempt_idx=attempt, places_count=0
            ):
                continue
            _raise_dedupe_empty_terminal()

        filtered = enrich_places(
            filtered,
            overnight_city=overnight,
            destination=str(trip.get("destination") or ""),
        )
        # Second pass: catch same venue under a new Google place_id / name key
        # after enrich rewrites addresses.
        filtered = dedupe_places(filtered, visited)
        if len(filtered) < 1:
            _note_dedupe_empty(places)
            if _will_retry_plan_day(
                code="dedupe_empty", attempt_idx=attempt, places_count=0
            ):
                continue
            _raise_dedupe_empty_terminal()
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
            if _will_retry_plan_day(
                code=exc.code,
                attempt_idx=attempt,
                places_count=len(filtered) if filtered else 0,
            ):
                continue
            # After retries, still return a usable day when meals are incomplete.
            if exc.code == "missing_meals" and filtered:
                if "missing_meals" not in energy_soft_tags:
                    energy_soft_tags = [*energy_soft_tags, "missing_meals"]
                last_quality_error = None
                break
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
    line = prior_day_summary_line(
        day_index=next_index,
        theme=theme,
        overnight_city=overnight,
        places=filtered,
    )
    prior_summary = append_prior_day_summary_line(prior, line)

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

