"""Plan-next-day *jobs*: claim a slot, enqueue worker, sync vs async entry.

Owns the planning-lock lifecycle (not the LLM work):

- ``plan_next_day`` — choose sync vs async from env
- ``start_plan_next_day`` — claim + GenAI charge + enqueue Event worker
- ``execute_plan_next_day`` — worker path after claim (calls the agent pipeline)
- ``plan_next_day_sync`` — fake/local path: run pipeline in-process
- Recover when a DAY already exists (finalize cursors without re-crewing)

Crew call + quality + persist live in ``trips.plan_day_agent_pipeline``.
Public wrappers for TripService live in ``trips.plan_day_api``.

Takes ``table`` / ``runner`` / ``safety`` / ``enqueue_plan_day`` as explicit
args — never imports ``trips.service.TripService`` (ADR 005).
"""

from __future__ import annotations

from typing import Any, Callable

from crews.runner import CrewRunner
from db import repository as repo
from db.protocols import DynamoDBTable
from http_utils import ApiError, client_facing_message, public_item
from ops.plan_day_worker import (
    enqueue_plan_next_day_worker,
    plan_next_day_async_enabled,
)
from safety.gate import SafetyGate

from trips.crud import _load_owned_bundle, _require_trip
from trips.day_index import resolve_plan_day_index
from trips.plan_day_agent_pipeline import (
    _cursors_from_existing_day,
    _run_plan_day_and_persist,
)


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


def plan_next_day_sync(
    *,
    user_sub: str,
    trip_id: str,
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
    email: str | None = None,
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
        email=email,
    )


def start_plan_next_day(
    *,
    user_sub: str,
    trip_id: str,
    table: DynamoDBTable | None,
    runner: CrewRunner,
    safety: SafetyGate,
    enqueue_plan_day: Callable[[str, str, int], None] | None,
    email: str | None = None,
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
    # If we clear a stale claim for day N, do not charge GenAI again for the same N.
    stale_reclaim_day: int | None = None
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
                stale_reclaim_day = claimed_i
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

    from limits.genai import consume_genai_action, refund_genai_action
    from user_profile.service import ProfileService

    profile = ProfileService(table=table, safety=safety).get_profile(
        user_sub, email=email
    )
    charge_genai = stale_reclaim_day != next_index

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

    if charge_genai:
        try:
            consume_genai_action(
                user_sub=user_sub, profile=profile, email=email, table=table
            )
        except ApiError:
            repo.fail_planning_in_progress(
                user_sub=user_sub,
                trip_id=trip_id,
                planned_day_index=next_index,
                error_message=client_facing_message(
                    status_code=429,
                    code="genai_quota_exceeded",
                    detail="GenAI usage limit reached",
                ),
                table=table,
            )
            raise
        except Exception as exc:
            # Dynamo/client failures must not leave planning_day_index stuck.
            repo.fail_planning_in_progress(
                user_sub=user_sub,
                trip_id=trip_id,
                planned_day_index=next_index,
                error_message=client_facing_message(
                    status_code=500,
                    code="internal_error",
                    detail=f"usage counter failed: {type(exc).__name__}",
                ),
                table=table,
            )
            raise ApiError(
                500,
                client_facing_message(
                    status_code=500,
                    code="internal_error",
                    detail="failed to record GenAI usage",
                ),
                code="internal_error",
            ) from exc

    enqueue = enqueue_plan_day or enqueue_plan_next_day_worker
    try:
        enqueue(user_sub, trip_id, next_index)
    except Exception as exc:
        if charge_genai:
            refund_genai_action(
                user_sub=user_sub, profile=profile, email=email, table=table
            )
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
    email: str | None = None,
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
            email=email,
        )
    return plan_next_day_sync(
        user_sub=user_sub,
        trip_id=trip_id,
        table=table,
        runner=runner,
        safety=safety,
        email=email,
    )
