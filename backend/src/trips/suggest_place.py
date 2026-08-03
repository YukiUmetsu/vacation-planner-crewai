"""Suggest one place onto an existing day (sync + async crew job).

Per ADR 005: takes ``table`` / ``runner`` / ``safety`` as explicit args and must
never import ``trips.service.TripService``. May import ``trips.crud``,
``trips.day_index``, and ``trips.prompts`` (one-way). Does not import
``trips.plan_day`` / plan-day jobs (keeps suggest independent of plan graph).
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
    hint_requires_non_food,
    is_food_like_suggest_hint,
    min_non_food_places_for,
    prefer_non_food_suggestion,
    require_suggested_place_balance,
    require_suggested_place_matches_hint,
)
from shared.energy import MAX_PLACES_PER_DAY, clamp_energy_level, max_minutes_for_energy
from planning_quality.place_quality import (
    day_total_minutes,
    profile_visited_name_keys,
    validate_suggested_place,
)
from planning_quality.suggest_place_retry import (
    MAX_SUGGEST_PLACE_ATTEMPTS,
    apply_suggest_place_retry_inputs,
    merge_banned_labels,
    rejected_suggest_labels,
    should_retry_suggest_place,
)
from crew_io.envelope import unwrap_crew_payload
from ops.worker_observability import log_plan_day_retry, log_quality_metrics
from places.client import PlacesTransientError
from places.enrich import enrich_place
from user_profile.service import ProfileService
from safety.gate import SafetyGate, check_texts
from safety.output import check_and_sanitize_place

from trips.crud import _json_safe, _load_owned_bundle, _require_trip
from trips.prompts import _merge_preferences, _profile_visited_keys

logger = logging.getLogger(__name__)


def suggest_place(
    *,
    user_sub: str,
    trip_id: str,
    day_index: int,
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
    email: str | None = None,
    enqueue_crew_job: Any | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Research and append one place to an existing planned day."""
    from ops.crew_async import llm_async_enabled

    req = _parse_suggest_place_request(body)
    if llm_async_enabled():
        return start_suggest_place(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            table=table,
            safety=safety,
            email=email,
            enqueue_crew_job=enqueue_crew_job,
            hint=req.hint,
        )
    return _suggest_place_sync(
        user_sub=user_sub,
        trip_id=trip_id,
        day_index=day_index,
        table=table,
        runner=runner,
        safety=safety,
        email=email,
        charge_genai=True,
        hint=req.hint,
    )


def _parse_suggest_place_request(body: dict[str, Any] | None):
    from pydantic import ValidationError

    from models.api import SuggestPlaceRequest

    try:
        return SuggestPlaceRequest.model_validate(body or {})
    except ValidationError as exc:
        msg = str(exc.errors()[0]["msg"]) if exc.errors() else "invalid request"
        raise ApiError(400, msg, code="invalid_request") from exc


def start_suggest_place(
    *,
    user_sub: str,
    trip_id: str,
    day_index: int,
    table: DynamoDBTable | None,
    safety: SafetyGate,
    email: str | None = None,
    enqueue_crew_job: Any | None = None,
    hint: str = "",
) -> dict[str, Any]:
    from limits.genai import consume_genai_action, refund_genai_action
    from ops.crew_job_worker import enqueue_crew_job_worker
    from user_profile.service import ProfileService

    if day_index < 1:
        raise ApiError(400, "day_index must be >= 1", code="invalid_day_index")

    trip = _require_trip(user_sub=user_sub, trip_id=trip_id, table=table)
    if trip.get("planning_day_index") is not None:
        raise ApiError(
            409,
            "cannot suggest a place while day planning is in progress",
            code="planning_in_progress",
        )
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
    # Light pre-crew safety on prefs so we don't claim then fail.
    interests = [str(i) for i in (profile.get("interests") or []) if str(i).strip()]
    merged_prefs = _merge_preferences(
        str(trip.get("preferences") or ""),
        str(profile.get("preferences") or ""),
        interests,
    )
    check_texts(
        safety,
        {
            "preferences": merged_prefs,
            "hint": hint or None,
            "origin": str(trip.get("origin") or ""),
            "destination": str(trip.get("destination") or ""),
        },
        trip_id=trip_id,
    )

    try:
        claimed = repo.claim_crew_job(
            user_sub=user_sub,
            trip_id=trip_id,
            kind=repo.JOB_SUGGEST_PLACE,
            day_index=day_index,
            baseline_place_count=len(existing),
            request={"hint": hint},
            table=table,
        )
    except repo.ConcurrentModificationError as exc:
        raise ApiError(409, str(exc), code="conflict") from exc

    try:
        consume_genai_action(
            user_sub=user_sub, profile=profile, email=email, table=table
        )
    except Exception as exc:
        repo.fail_crew_job(
            user_sub=user_sub,
            trip_id=trip_id,
            expected_kind=repo.JOB_SUGGEST_PLACE,
            error_message=client_facing_message(
                status_code=getattr(exc, "status_code", 500),
                code=getattr(exc, "code", "internal_error"),
                detail=str(getattr(exc, "message", exc)),
            ),
            table=table,
        )
        raise

    enqueue = enqueue_crew_job or enqueue_crew_job_worker
    try:
        enqueue(
            {
                "worker": repo.JOB_SUGGEST_PLACE,
                "user_sub": user_sub,
                "trip_id": trip_id,
                "day_index": day_index,
            }
        )
    except Exception as exc:
        refund_genai_action(
            user_sub=user_sub, profile=profile, email=email, table=table
        )
        repo.fail_crew_job(
            user_sub=user_sub,
            trip_id=trip_id,
            expected_kind=repo.JOB_SUGGEST_PLACE,
            error_message=client_facing_message(
                status_code=502,
                code="enqueue_failed",
                detail=f"failed to start suggest-place: {type(exc).__name__}",
            ),
            table=table,
        )
        raise ApiError(
            502,
            client_facing_message(
                status_code=502,
                code="enqueue_failed",
                detail="failed to start async suggest-place worker",
            ),
            code="enqueue_failed",
        ) from exc

    return {
        "async": True,
        "trip": public_item(claimed),
        "job": repo.JOB_SUGGEST_PLACE,
        "day_index": day_index,
        "baseline_place_count": len(existing),
    }


def execute_suggest_place(
    *,
    user_sub: str,
    trip_id: str,
    day_index: int,
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
) -> dict[str, Any]:
    trip = _require_trip(user_sub=user_sub, trip_id=trip_id, table=table)
    if trip.get("crew_job_kind") != repo.JOB_SUGGEST_PLACE:
        raise ApiError(409, "suggest-place job claim missing", code="conflict")
    claimed_day = trip.get("crew_job_day_index")
    try:
        claimed_i = int(claimed_day) if claimed_day is not None else None
    except (TypeError, ValueError):
        claimed_i = None
    if claimed_i != day_index:
        raise ApiError(409, "suggest-place day mismatch", code="conflict")

    # Idempotent recovery: place may already be written if we died after persist
    # and before complete_crew_job (Lambda Event retry must not append again).
    recovered = _recover_suggest_place_if_persisted(
        user_sub=user_sub,
        trip_id=trip_id,
        trip=trip,
        day_index=day_index,
        table=table,
    )
    if recovered is not None:
        return recovered

    req = trip.get("crew_job_request")
    hint = ""
    if isinstance(req, dict):
        hint = str(req.get("hint") or "").strip()
    try:
        return _suggest_place_sync(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            table=table,
            runner=runner,
            safety=safety,
            email=None,
            charge_genai=False,
            complete_job=True,
            hint=hint,
        )
    except ApiError as exc:
        # Retryable AgentCore transport: keep claim so Event retries can run.
        if not exc.retryable:
            repo.fail_crew_job(
                user_sub=user_sub,
                trip_id=trip_id,
                expected_kind=repo.JOB_SUGGEST_PLACE,
                error_message=client_facing_message(
                    status_code=exc.status_code,
                    code=exc.code or "crew_failed",
                    detail=exc.message,
                ),
                table=table,
            )
        raise
    except Exception as exc:
        repo.fail_crew_job(
            user_sub=user_sub,
            trip_id=trip_id,
            expected_kind=repo.JOB_SUGGEST_PLACE,
            error_message=client_facing_message(
                status_code=500,
                code="internal_error",
                detail=type(exc).__name__,
            ),
            table=table,
        )
        raise


def _recover_suggest_place_if_persisted(
    *,
    user_sub: str,
    trip_id: str,
    trip: dict[str, Any],
    day_index: int,
    table: DynamoDBTable | None,
) -> dict[str, Any] | None:
    """If DAY already grew past the claim baseline, clear claim and return it."""
    raw_baseline = trip.get("crew_job_baseline_place_count")
    try:
        baseline = int(raw_baseline) if raw_baseline is not None else None
    except (TypeError, ValueError):
        baseline = None
    if baseline is None:
        return None
    day = repo.get_day(
        user_sub=user_sub, trip_id=trip_id, day_index=day_index, table=table
    )
    if not day:
        return None
    places = list(day.get("places") or [])
    if len(places) <= baseline:
        return None
    completed = repo.complete_crew_job(
        user_sub=user_sub,
        trip_id=trip_id,
        expected_kind=repo.JOB_SUGGEST_PLACE,
        table=table,
    )
    place = places[-1]
    if not isinstance(place, dict):
        raise ApiError(500, "persisted place malformed", code="internal_error")
    return {
        "place": place,
        "day": public_item(day),
        "trip": public_item(completed),
    }


def _suggest_place_sync(
    *,
    user_sub: str,
    trip_id: str,
    day_index: int,
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
    email: str | None = None,
    charge_genai: bool = True,
    complete_job: bool = False,
    hint: str = "",
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
    hint = (hint or "").strip()
    honor_user_hint = bool(hint)
    honor_food_hint = is_food_like_suggest_hint(hint)
    food_crawl_mode = detect_food_crawl_mode(merged_prefs, interests)
    min_non_food = min_non_food_places_for(food_crawl_mode=food_crawl_mode)
    prefer_non_food = prefer_non_food_suggestion(
        existing,
        food_crawl_mode=food_crawl_mode,
        honor_food_hint=honor_food_hint,
    )
    # With a one-off hint, skip day-balance preference lines so the dedicated
    # crew ``hint`` input stays the clear priority (no duplicate pref prose).
    if not honor_user_hint:
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
    crew_preferences = merged_prefs
    crew_interests = ", ".join(interests)
    if honor_user_hint:
        # Trip/profile prefs stay secondary to the one-off hint.
        if crew_preferences:
            crew_preferences = (
                "One-off hint for THIS stop is the primary request — do not "
                "override it with trip preferences. Trip background "
                f"(secondary, only if compatible with the hint): {crew_preferences}"
            )
        else:
            crew_preferences = (
                "One-off hint for THIS stop is the primary request — do not "
                "override it with trip preferences."
            )
        if hint_requires_non_food(hint):
            # Steer first crew attempt; prompts only ban food when hint is empty
            # + prefer_non_food, so put the rule in the preferences payload.
            non_food_line = (
                "Use a non-food category; avoid restaurants and cafes."
            )
            crew_preferences = f"{non_food_line} {crew_preferences}".strip()
        if crew_interests:
            crew_interests = (
                "Interests (secondary to hint, only if compatible): "
                f"{crew_interests}"
            )
    # Pre-crew gate: safety rejection must not consume GenAI quota.
    check_texts(
        safety,
        {
            "preferences": crew_preferences,
            "hint": hint or None,
            "origin": str(trip.get("origin") or ""),
            "destination": str(trip.get("destination") or ""),
            "prior_days_summary": str(trip.get("prior_days_summary") or ""),
        },
        trip_id=trip_id,
    )
    if charge_genai:
        consume_genai_action(
            user_sub=user_sub, profile=profile, email=email, table=table
        )

    current_total = day_total_minutes(existing)
    # Comfort remaining only — never send negative minutes into the crew.
    remaining = max(0, max_minutes - current_total)

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
    base_inputs = slim_crew_inputs(
        {
            "overnight_city": overnight,
            "day_index": str(day_index),
            "date": day_date.isoformat(),
            "preferences": crew_preferences,
            "hint": hint,
            "interests": crew_interests,
            "food_crawl_mode": "true" if food_crawl_mode else "false",
            "prefer_non_food": "true" if prefer_non_food else "false",
            "min_non_food_places": str(min_non_food),
            "energy_level": str(energy_level),
            "remaining_minutes": str(remaining),
            "already_visited": ",".join(visited),
            "prior_days_summary": str(trip.get("prior_days_summary") or ""),
            "current_places_json": json.dumps(_json_safe(slim_current)),
            "next_order_in_day": str(len(existing) + 1),
        },
        overnight_city=overnight,
        day_index=day_index,
    )

    banned: list[str] = []
    last_quality_error: ApiError | None = None
    validated: dict[str, Any] | None = None
    energy_soft_tags: list[str] = []

    for attempt in range(MAX_SUGGEST_PLACE_ATTEMPTS):
        inputs = apply_suggest_place_retry_inputs(
            base_inputs,
            attempt=attempt,
            failure_code=(
                str(last_quality_error.code) if last_quality_error is not None else None
            ),
            plan_date=day_date,
            banned_places=banned,
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
        try:
            # Enforce prior closed/rejected bans in validation (not prompt-only).
            validate_visited = set(visited) | set(banned)
            validated, energy_soft_tags = validate_suggested_place(
                candidate,
                existing_places=existing,
                plan_date=day_date,
                max_comfortable_minutes=max_minutes,
                already_visited_keys=validate_visited,
                profile_visited_names=profile_visited_name_keys(
                    list(profile.get("visited_places") or [])
                ),
            )
            require_suggested_place_matches_hint(
                validated,
                hint=hint,
            )
            # Hint check first so food/category mismatches use retryable
            # hint_mismatch instead of non-retryable food_only_day.
            require_suggested_place_balance(
                validated,
                existing,
                food_crawl_mode=food_crawl_mode,
                honor_food_hint=honor_food_hint,
            )
            last_quality_error = None
            break
        except ApiError as exc:
            last_quality_error = exc
            if should_retry_suggest_place(code=exc.code, attempt=attempt):
                banned = merge_banned_labels(
                    banned, rejected_suggest_labels(candidate)
                )
                log_plan_day_retry(
                    trip_id=trip_id,
                    day_index=day_index,
                    attempt=attempt + 1,
                    failure_code=str(exc.code or "unknown"),
                    invocation={"suggest_place_attempt": attempt + 1},
                    places_count=1,
                )
                continue
            raise

    if last_quality_error is not None:
        raise last_quality_error
    if validated is None:
        raise ApiError(500, "suggest place missing after retries", code="internal_error")
    validated = check_and_sanitize_place(safety, validated, trip_id=trip_id)
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

    if complete_job:
        trip = repo.complete_crew_job(
            user_sub=user_sub,
            trip_id=trip_id,
            expected_kind=repo.JOB_SUGGEST_PLACE,
            table=table,
        )

    return {
        "place": validated,
        "day": public_item(day_item),
        "trip": public_item(trip),
    }

