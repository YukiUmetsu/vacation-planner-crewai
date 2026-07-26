"""Non-persisting GenAI city suggestions for an existing draft route."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from crew_io.context_budget import slim_crew_inputs
from crew_io.envelope import unwrap_crew_payload
from crews.runner import CrewRunner, crew_mode
from db.protocols import DynamoDBTable
from http_utils import ApiError, client_facing_message, public_item
from limits.genai import consume_genai_action
from models.api import SuggestCityDraftStop, SuggestCityRequest
from ops.worker_observability import WorkerTimer, log_crew_duration
from safety.gate import SafetyGate
from shared.route_windows import max_cities_for_trip
from trips.crud import _json_safe, _load_owned_bundle
from user_profile.service import ProfileService

_MAX_COUNT = 3


def _norm_city(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().casefold())


def _city_names(cities: list[Any]) -> list[str]:
    names: list[str] = []
    for stop in cities:
        if isinstance(stop, str):
            raw = stop.strip()
        elif isinstance(stop, dict):
            raw = str(stop.get("city") or "").strip()
        else:
            continue
        if raw:
            names.append(raw)
    return names


def _unique_names(*groups: list[str]) -> list[str]:
    """Preserve first-seen order across name groups."""
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for name in group:
            key = _norm_city(name)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(name.strip())
    return out


def _parse_request(body: dict[str, Any] | None) -> SuggestCityRequest:
    try:
        return SuggestCityRequest.model_validate(body or {})
    except ValidationError as exc:
        msg = str(exc.errors()[0]["msg"]) if exc.errors() else "invalid request"
        raise ApiError(400, msg, code="invalid_request") from exc


def _draft_dicts(stops: list[SuggestCityDraftStop]) -> list[dict[str, Any]]:
    return [
        {
            "city": s.city,
            "country": s.country,
            "nights": s.nights,
            "reason": s.reason,
            "highlights": list(s.highlights),
        }
        for s in stops
    ]


def _safety_check_draft(
    safety: SafetyGate,
    *,
    hint: str,
    draft: list[SuggestCityDraftStop] | None,
) -> None:
    if hint:
        safety.check_text(hint, source="hint")
    if not draft:
        return
    for index, stop in enumerate(draft):
        safety.check_text(stop.city, source=f"cities[{index}].city")
        if stop.country:
            safety.check_text(stop.country, source=f"cities[{index}].country")
        if stop.reason:
            safety.check_text(stop.reason, source=f"cities[{index}].reason")
        for hi, highlight in enumerate(stop.highlights):
            safety.check_text(highlight, source=f"cities[{index}].highlights[{hi}]")


def _dedupe_candidates(
    candidates: list[dict[str, Any]],
    *,
    banned: set[str],
    limit: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        city = str(raw.get("city") or "").strip()
        key = _norm_city(city)
        if not city or not key or key in banned or key in seen:
            continue
        try:
            nights = int(raw.get("recommended_nights") or 1)
        except (TypeError, ValueError):
            nights = 1
        if nights < 1:
            continue
        highlights = raw.get("highlights") or []
        if not isinstance(highlights, list):
            highlights = []
        out.append(
            {
                "city": city,
                "country": str(raw.get("country") or "").strip(),
                "reason": str(raw.get("reason") or "").strip(),
                "highlights": [str(h).strip() for h in highlights if str(h).strip()][
                    :3
                ],
                "recommended_nights": nights,
            }
        )
        seen.add(key)
        if len(out) >= limit:
            break
    return out


def suggest_city(
    *,
    user_sub: str,
    trip_id: str,
    body: dict[str, Any] | None,
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
    email: str | None = None,
    enqueue_crew_job: Any | None = None,
) -> dict[str, Any]:
    """Return CitySuggestion candidates; does not mutate ROUTE."""
    from ops.crew_async import llm_async_enabled

    if llm_async_enabled():
        return start_suggest_city(
            user_sub=user_sub,
            trip_id=trip_id,
            body=body,
            table=table,
            safety=safety,
            email=email,
            enqueue_crew_job=enqueue_crew_job,
        )
    return _suggest_city_sync(
        user_sub=user_sub,
        trip_id=trip_id,
        body=body,
        table=table,
        runner=runner,
        safety=safety,
        email=email,
        charge_genai=True,
    )


def start_suggest_city(
    *,
    user_sub: str,
    trip_id: str,
    body: dict[str, Any] | None,
    table: DynamoDBTable | None,
    safety: SafetyGate,
    email: str | None = None,
    enqueue_crew_job: Any | None = None,
) -> dict[str, Any]:
    from limits.genai import refund_genai_action
    from ops.crew_job_worker import enqueue_crew_job_worker
    from user_profile.service import ProfileService
    from db import repository as repo

    req = _parse_request(body)
    trip, route, _days = _load_owned_bundle(
        user_sub=user_sub, trip_id=trip_id, table=table
    )
    if str(trip.get("status") or "") == "deleting":
        raise ApiError(409, "trip is being deleted", code="trip_deleting")
    if trip.get("planning_day_index") is not None:
        raise ApiError(
            409,
            "cannot suggest a city while day planning is in progress",
            code="planning_in_progress",
        )

    day_count = int(trip.get("day_count") or 0)
    if day_count < 1:
        raise ApiError(400, "trip day_count invalid", code="invalid_trip")

    max_cities = max_cities_for_trip(day_count=day_count)
    persisted = list((route or {}).get("cities") or [])
    persisted_names = _city_names(persisted)
    draft = req.cities
    draft_names = _city_names(_draft_dicts(draft)) if draft is not None else []
    listed = _unique_names(persisted_names, draft_names)
    if len(listed) >= max_cities:
        raise ApiError(
            409,
            f"route already has the maximum of {max_cities} cities for this trip",
            code="city_cap",
        )

    count = max(1, min(int(req.count), _MAX_COUNT))
    count = min(count, max_cities - len(listed))
    _safety_check_draft(safety, hint=req.hint, draft=draft)
    safety.check_text(str(trip.get("preferences") or ""), source="preferences")
    safety.check_text(str(trip.get("destination") or ""), source="destination")

    profile = ProfileService(table=table, safety=safety).get_profile(
        user_sub, email=email
    )
    request_blob = {
        "hint": req.hint,
        "count": count,
        "cities": _draft_dicts(draft) if draft is not None else None,
    }
    try:
        claimed = repo.claim_crew_job(
            user_sub=user_sub,
            trip_id=trip_id,
            kind=repo.JOB_SUGGEST_CITY,
            request=request_blob,
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
            expected_kind=repo.JOB_SUGGEST_CITY,
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
                "worker": repo.JOB_SUGGEST_CITY,
                "user_sub": user_sub,
                "trip_id": trip_id,
            }
        )
    except Exception as exc:
        refund_genai_action(
            user_sub=user_sub, profile=profile, email=email, table=table
        )
        repo.fail_crew_job(
            user_sub=user_sub,
            trip_id=trip_id,
            expected_kind=repo.JOB_SUGGEST_CITY,
            error_message=client_facing_message(
                status_code=502,
                code="enqueue_failed",
                detail=f"failed to start suggest-city: {type(exc).__name__}",
            ),
            table=table,
        )
        raise ApiError(
            502,
            client_facing_message(
                status_code=502,
                code="enqueue_failed",
                detail="failed to start async suggest-city worker",
            ),
            code="enqueue_failed",
        ) from exc

    return {
        "async": True,
        "trip": public_item(claimed),
        "job": repo.JOB_SUGGEST_CITY,
    }


def execute_suggest_city(
    *,
    user_sub: str,
    trip_id: str,
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
) -> dict[str, Any]:
    from db import repository as repo

    trip, _route, _days = _load_owned_bundle(
        user_sub=user_sub, trip_id=trip_id, table=table
    )
    if trip.get("crew_job_kind") != repo.JOB_SUGGEST_CITY:
        raise ApiError(409, "suggest-city job claim missing", code="conflict")
    body = trip.get("crew_job_request")
    if not isinstance(body, dict):
        body = {}
    try:
        return _suggest_city_sync(
            user_sub=user_sub,
            trip_id=trip_id,
            body=body,
            table=table,
            runner=runner,
            safety=safety,
            email=None,
            charge_genai=False,
            complete_job=True,
        )
    except ApiError as exc:
        # Retryable AgentCore transport: keep claim so Event retries can run.
        if not exc.retryable:
            repo.fail_crew_job(
                user_sub=user_sub,
                trip_id=trip_id,
                expected_kind=repo.JOB_SUGGEST_CITY,
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
            expected_kind=repo.JOB_SUGGEST_CITY,
            error_message=client_facing_message(
                status_code=500,
                code="internal_error",
                detail=type(exc).__name__,
            ),
            table=table,
        )
        raise


def _suggest_city_sync(
    *,
    user_sub: str,
    trip_id: str,
    body: dict[str, Any] | None,
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
    email: str | None = None,
    charge_genai: bool = True,
    complete_job: bool = False,
) -> dict[str, Any]:
    """Return CitySuggestion candidates; does not mutate ROUTE."""
    from db import repository as repo

    req = _parse_request(body)
    trip, route, _days = _load_owned_bundle(
        user_sub=user_sub, trip_id=trip_id, table=table
    )
    if str(trip.get("status") or "") == "deleting":
        raise ApiError(409, "trip is being deleted", code="trip_deleting")

    day_count = int(trip.get("day_count") or 0)
    if day_count < 1:
        raise ApiError(400, "trip day_count invalid", code="invalid_trip")

    max_cities = max_cities_for_trip(day_count=day_count)
    persisted = list((route or {}).get("cities") or [])
    persisted_names = _city_names(persisted)
    draft = req.cities
    draft_names = _city_names(_draft_dicts(draft)) if draft is not None else []

    # Dedupe ban list always includes persisted cities even if the client omits them.
    listed = _unique_names(persisted_names, draft_names)
    if len(listed) >= max_cities:
        raise ApiError(
            409,
            f"route already has the maximum of {max_cities} cities for this trip",
            code="city_cap",
        )

    count = max(1, min(int(req.count), _MAX_COUNT))
    count = min(count, max_cities - len(listed))

    _safety_check_draft(safety, hint=req.hint, draft=draft)
    safety.check_text(str(trip.get("preferences") or ""), source="preferences")
    safety.check_text(str(trip.get("destination") or ""), source="destination")

    profile = ProfileService(table=table, safety=safety).get_profile(
        user_sub, email=email
    )
    if charge_genai:
        consume_genai_action(
            user_sub=user_sub, profile=profile, email=email, table=table
        )

    interests = ""
    if isinstance(profile, dict):
        raw_interests = profile.get("interests") or []
        if isinstance(raw_interests, list):
            interests = ", ".join(str(x) for x in raw_interests if str(x).strip())

    # Crew context: prefer sanitized draft when provided; ban list still unions persisted.
    current_for_crew = _draft_dicts(draft) if draft is not None else persisted
    banned = {_norm_city(n) for n in listed}
    inputs = slim_crew_inputs(
        {
            "origin": str(trip.get("origin") or ""),
            "destination": str(trip.get("destination") or ""),
            "destination_type": str(trip.get("destination_type") or "country"),
            "start_date": str(trip.get("start_date") or ""),
            "end_date": str(trip.get("end_date") or ""),
            "day_count": str(day_count),
            "preferences": str(trip.get("preferences") or ""),
            "interests": interests,
            "hint": req.hint,
            "count": str(count),
            "already_listed_cities": ", ".join(listed),
            "current_cities_json": json.dumps(
                _json_safe(current_for_crew), ensure_ascii=False
            ),
        }
    )

    timer = WorkerTimer()
    raw = runner.suggest_city(inputs)
    extracted, _, _ = unwrap_crew_payload(raw)
    log_crew_duration(
        operation="suggest_city",
        trip_id=trip_id,
        duration_ms=timer.duration_ms(),
        extra={"crew_mode": crew_mode()},
    )

    if (
        isinstance(extracted, dict)
        and "error" in extracted
        and "candidates" not in extracted
    ):
        raise ApiError(
            502,
            str(extracted.get("error") or "suggest_city failed"),
            code="crew_failed",
        )

    if isinstance(extracted, dict) and isinstance(extracted.get("candidates"), list):
        candidates_raw = extracted["candidates"]
    elif isinstance(extracted, list):
        candidates_raw = extracted
    elif isinstance(extracted, dict) and extracted.get("city"):
        candidates_raw = [extracted]
    else:
        candidates_raw = []

    candidates = _dedupe_candidates(candidates_raw, banned=banned, limit=count)
    if not candidates:
        raise ApiError(
            502,
            "no new city suggestions available (duplicates or empty result)",
            code="suggest_city_empty",
        )

    if complete_job:
        trip_out = repo.complete_crew_job(
            user_sub=user_sub,
            trip_id=trip_id,
            expected_kind=repo.JOB_SUGGEST_CITY,
            extra_sets={"suggest_city_candidates": candidates},
            table=table,
        )
        return {
            "candidates": candidates,
            "trip": public_item(trip_out),
        }

    return {
        "candidates": candidates,
        "trip": public_item(trip),
    }
