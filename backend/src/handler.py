"""API Gateway Lambda entry."""

from __future__ import annotations

import logging
from typing import Any

from auth import (
    apply_dev_crew_mode_override,
    clear_dev_crew_mode_override,
    get_user_sub,
)
from db import repository as repo
from http_utils import (
    ApiError,
    client_facing_message,
    error_response,
    json_response,
    parse_day_action,
    parse_day_place,
    parse_day_resource,
    parse_route,
    request_method,
    request_path,
)
from log_config import configure_logging
from routes import profile as profile_routes
from routes import trips as trip_routes
from services.plan_day_worker import is_plan_next_day_worker_event
from services.trip_service import TripService
from services.worker_observability import WorkerTimer, log_worker_outcome

configure_logging()
logger = logging.getLogger(__name__)


def _request_id(context: Any) -> str:
    rid = getattr(context, "aws_request_id", None) if context is not None else None
    return str(rid) if rid else "-"


def _log_api_error(
    exc: ApiError,
    *,
    method: str,
    path: str,
    request_id: str,
) -> None:
    """Emit a single CloudWatch-searchable line for every ApiError response."""
    # Keep operator detail in logs even when the HTTP body is sanitized.
    msg = (
        f"API_ERROR status={exc.status_code} code={exc.code or '-'} "
        f"method={method} path={path} request_id={request_id} "
        f"msg={exc.message!r}"
    )
    if exc.status_code >= 500:
        logger.error(msg)
    else:
        logger.warning(msg)


def _planning_claim_held(
    *,
    user_sub: str,
    trip_id: str,
    day_index: int,
    table: Any | None = None,
) -> bool:
    trip = repo.get_trip_meta(user_sub=user_sub, trip_id=trip_id, table=table)
    if not trip:
        return False
    claimed = trip.get("planning_day_index")
    try:
        return int(claimed) == day_index if claimed is not None else False
    except (TypeError, ValueError):
        return False


def _handle_plan_next_day_worker(event: dict[str, Any]) -> dict[str, Any]:
    """Run the Event self-invoke worker.

    On failure: log, then **re-raise while the planning claim is still held** so
    Lambda ``InvocationType=Event`` retries can run (default: 2). That recovers
    transient DynamoDB blips and the ``DAY written / cursor not advanced`` case.

    If ``execute_plan_next_day`` already cleared the claim (terminal
    ``fail_planning_in_progress``), return without raising so Lambda does not burn
    useless retries — client/BFF reclaim paths own recovery from there.
    """
    user_sub = str(event["user_sub"])
    trip_id = str(event["trip_id"])
    day_index = int(event["day_index"])
    service = TripService()
    timer = WorkerTimer()
    try:
        service.execute_plan_next_day(user_sub, trip_id, day_index)
    except Exception as exc:
        duration_ms = timer.duration_ms()
        retryable = isinstance(exc, ApiError) and bool(exc.retryable)
        claim_held = _planning_claim_held(
            user_sub=user_sub,
            trip_id=trip_id,
            day_index=day_index,
            table=getattr(service, "_table", None),
        )
        # Prefer claim_held for Event retry: non-ApiError transients also retry.
        will_retry = claim_held
        logger.exception(
            "plan_next_day worker failed trip_id=%s day_index=%s",
            trip_id,
            day_index,
        )
        log_worker_outcome(
            trip_id=trip_id,
            day_index=day_index,
            outcome="retry" if will_retry else "terminal",
            duration_ms=duration_ms,
            # ApiError.retryable only — do not OR with claim_held (outcome already says retry).
            retryable=retryable if isinstance(exc, ApiError) else None,
            error_code=getattr(exc, "code", None) if isinstance(exc, ApiError) else None,
            error_type=type(exc).__name__,
        )
        if will_retry:
            raise
        return {"ok": False, "terminal": True}

    log_worker_outcome(
        trip_id=trip_id,
        day_index=day_index,
        outcome="success",
        duration_ms=timer.duration_ms(),
    )
    return {"ok": True}


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    configure_logging()
    if is_plan_next_day_worker_event(event):
        return _handle_plan_next_day_worker(event)

    method = "-"
    path = "-"
    crew_override_token = apply_dev_crew_mode_override(event)
    try:
        method = request_method(event)
        path = request_path(event)

        if method == "OPTIONS":
            return json_response(200, {"ok": True})

        user_sub = get_user_sub(event)
        trip_id, action = parse_route(path)

        if path == "/profile" or path.rstrip("/") == "/profile":
            if method == "GET":
                return json_response(200, profile_routes.get_profile(event, user_sub))
            if method == "PUT":
                return json_response(200, profile_routes.put_profile(event, user_sub))
            raise ApiError(405, f"method {method} not allowed")

        if path == "/trips" or path.rstrip("/") == "/trips":
            if method == "POST":
                return json_response(201, trip_routes.create_trip(event, user_sub))
            if method == "GET":
                return json_response(200, trip_routes.list_trips(event, user_sub))
            raise ApiError(405, f"method {method} not allowed")

        if trip_id and action is None and path.startswith("/trips/"):
            if method == "GET":
                return json_response(200, trip_routes.get_trip(event, user_sub, trip_id))
            if method == "PUT":
                return json_response(
                    200, trip_routes.update_trip(event, user_sub, trip_id)
                )
            if method == "DELETE":
                return json_response(
                    200, trip_routes.delete_trip(event, user_sub, trip_id)
                )
            raise ApiError(405, f"method {method} not allowed")

        if trip_id and action == "propose-cities":
            if method == "POST":
                return json_response(200, trip_routes.propose_cities(event, user_sub, trip_id))
            raise ApiError(405, f"method {method} not allowed")

        if trip_id and action == "cities":
            if method == "PUT":
                return json_response(200, trip_routes.confirm_cities(event, user_sub, trip_id))
            raise ApiError(405, f"method {method} not allowed")

        if trip_id and action == "plan-next-day":
            if method == "POST":
                result = trip_routes.plan_next_day(event, user_sub, trip_id)
                if result.get("async"):
                    return json_response(
                        202,
                        {
                            "trip": result["trip"],
                            "planning_day_index": result["planning_day_index"],
                        },
                    )
                return json_response(
                    200,
                    {"day": result["day"], "trip": result["trip"]},
                )
            raise ApiError(405, f"method {method} not allowed")

        day_route = parse_day_action(path)
        if day_route:
            day_trip_id, day_index, day_action = day_route
            if day_action == "suggest-place":
                if method == "POST":
                    return json_response(
                        200,
                        trip_routes.suggest_place(
                            event, user_sub, day_trip_id, day_index
                        ),
                    )
                raise ApiError(405, f"method {method} not allowed")

        day_place = parse_day_place(path)
        if day_place:
            day_trip_id, day_index, place_index = day_place
            if method == "DELETE":
                return json_response(
                    200,
                    trip_routes.remove_place(
                        event, user_sub, day_trip_id, day_index, place_index
                    ),
                )
            raise ApiError(405, f"method {method} not allowed")

        day_resource = parse_day_resource(path)
        if day_resource:
            day_trip_id, day_index = day_resource
            if method == "DELETE":
                return json_response(
                    200,
                    trip_routes.delete_day(event, user_sub, day_trip_id, day_index),
                )
            raise ApiError(405, f"method {method} not allowed")

        raise ApiError(404, f"route not found: {method} {path}", code="not_found")
    except ApiError as exc:
        _log_api_error(
            exc,
            method=method,
            path=path,
            request_id=_request_id(context),
        )
        return error_response(exc)
    except Exception:  # noqa: BLE001 — Lambda boundary; do not leak internals
        logger.exception(
            "API_ERROR status=500 code=internal_error method=%s path=%s request_id=%s",
            method if method != "-" else request_method(event),
            path if path != "-" else request_path(event),
            _request_id(context),
        )
        return json_response(
            500,
            {
                "error": client_facing_message(
                    status_code=500,
                    code="internal_error",
                    detail="internal server error",
                ),
                "code": "internal_error",
            },
        )
    finally:
        clear_dev_crew_mode_override(crew_override_token)
