"""API Gateway Lambda entry."""

from __future__ import annotations

from typing import Any

from auth import get_user_sub
from http_utils import (
    ApiError,
    error_response,
    json_response,
    parse_day_action,
    parse_route,
    request_method,
    request_path,
)
from routes import profile as profile_routes
from routes import trips as trip_routes


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
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
                return json_response(200, trip_routes.plan_next_day(event, user_sub, trip_id))
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

        raise ApiError(404, f"route not found: {method} {path}", code="not_found")
    except ApiError as exc:
        return error_response(exc)
    except Exception:  # noqa: BLE001 — Lambda boundary; do not leak internals
        return json_response(
            500,
            {"error": "internal server error", "code": "internal_error"},
        )
