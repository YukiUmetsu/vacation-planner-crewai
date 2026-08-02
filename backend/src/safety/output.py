"""Helpers to run OUTPUT safety + link sanitize on structured crew results."""

from __future__ import annotations

from typing import Any

from safety.gate import SafetyGate, check_texts
from safety.sanitize import sanitize_ai_prose, sanitize_places


def day_plan_output_fields(plan: dict[str, Any]) -> dict[str, str | None]:
    fields: dict[str, str | None] = {
        "theme": str(plan.get("theme") or "") or None,
        "summary": str(plan.get("summary") or "") or None,
    }
    places = plan.get("places") if isinstance(plan.get("places"), list) else []
    for index, place in enumerate(places):
        if not isinstance(place, dict):
            continue
        fields[f"places[{index}].name"] = str(place.get("name") or "") or None
        fields[f"places[{index}].reason_to_visit"] = (
            str(place.get("reason_to_visit") or place.get("reason") or "") or None
        )
        fields[f"places[{index}].details"] = str(place.get("details") or "") or None
        fields[f"places[{index}].maps_url"] = str(
            place.get("maps_url") or place.get("map_url") or ""
        ) or None
        fields[f"places[{index}].website_url"] = (
            str(place.get("website_url") or "") or None
        )
    return fields


def sanitize_day_plan(plan: dict[str, Any]) -> dict[str, Any]:
    out = dict(plan)
    if isinstance(out.get("theme"), str):
        out["theme"] = sanitize_ai_prose(out["theme"])
    if isinstance(out.get("summary"), str):
        out["summary"] = sanitize_ai_prose(out["summary"])
    if isinstance(out.get("places"), list):
        out["places"] = sanitize_places(out["places"])
    return out


def check_and_sanitize_day_plan(
    gate: SafetyGate,
    plan: dict[str, Any],
    *,
    trip_id: str | None = None,
) -> dict[str, Any]:
    check_texts(
        gate,
        day_plan_output_fields(plan),
        direction="output",
        trip_id=trip_id,
    )
    return sanitize_day_plan(plan)


def city_candidate_output_fields(candidates: list[Any]) -> dict[str, str | None]:
    fields: dict[str, str | None] = {}
    for index, raw in enumerate(candidates):
        if not isinstance(raw, dict):
            continue
        fields[f"candidates[{index}].city"] = str(raw.get("city") or "") or None
        fields[f"candidates[{index}].country"] = str(raw.get("country") or "") or None
        fields[f"candidates[{index}].reason"] = str(raw.get("reason") or "") or None
        highlights = raw.get("highlights") if isinstance(raw.get("highlights"), list) else []
        for hi, highlight in enumerate(highlights):
            fields[f"candidates[{index}].highlights[{hi}]"] = str(highlight or "") or None
    return fields


def sanitize_city_candidates(candidates: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        for key in ("city", "country", "reason"):
            if isinstance(item.get(key), str):
                item[key] = sanitize_ai_prose(item[key])
        if isinstance(item.get("highlights"), list):
            item["highlights"] = [
                sanitize_ai_prose(str(h)) if h is not None else h
                for h in item["highlights"]
            ]
        out.append(item)
    return out


def check_and_sanitize_city_candidates(
    gate: SafetyGate,
    candidates: list[Any],
    *,
    trip_id: str | None = None,
) -> list[dict[str, Any]]:
    check_texts(
        gate,
        city_candidate_output_fields(candidates),
        direction="output",
        trip_id=trip_id,
    )
    return sanitize_city_candidates(candidates)


def suggest_place_output_fields(place: dict[str, Any]) -> dict[str, str | None]:
    return {
        "place.name": str(place.get("name") or "") or None,
        "place.reason_to_visit": (
            str(place.get("reason_to_visit") or place.get("reason") or "") or None
        ),
        "place.details": str(place.get("details") or "") or None,
        "place.maps_url": str(place.get("maps_url") or place.get("map_url") or "")
        or None,
        "place.website_url": str(place.get("website_url") or "") or None,
    }


def check_and_sanitize_place(
    gate: SafetyGate,
    place: dict[str, Any],
    *,
    trip_id: str | None = None,
) -> dict[str, Any]:
    check_texts(
        gate,
        suggest_place_output_fields(place),
        direction="output",
        trip_id=trip_id,
    )
    from safety.sanitize import sanitize_place_dict

    return sanitize_place_dict(place)


def city_route_output_fields(route: dict[str, Any]) -> dict[str, str | None]:
    fields: dict[str, str | None] = {
        "route.summary": str(route.get("summary") or "") or None,
        "route.rationale": str(route.get("rationale") or "") or None,
    }
    cities = route.get("cities") if isinstance(route.get("cities"), list) else []
    # Also support stops / city_stops shapes used in this codebase.
    stops = cities or route.get("stops") or route.get("city_stops") or []
    if not isinstance(stops, list):
        stops = []
    for index, stop in enumerate(stops):
        if not isinstance(stop, dict):
            continue
        fields[f"route.cities[{index}].city"] = str(
            stop.get("city") or stop.get("name") or ""
        ) or None
        fields[f"route.cities[{index}].reason"] = str(
            stop.get("reason") or stop.get("rationale") or ""
        ) or None
        highlights = (
            stop.get("highlights") if isinstance(stop.get("highlights"), list) else []
        )
        for hi, highlight in enumerate(highlights):
            fields[f"route.cities[{index}].highlights[{hi}]"] = (
                str(highlight or "") or None
            )
    return fields


def check_and_sanitize_city_route(
    gate: SafetyGate,
    route: dict[str, Any],
    *,
    trip_id: str | None = None,
) -> dict[str, Any]:
    check_texts(
        gate,
        city_route_output_fields(route),
        direction="output",
        trip_id=trip_id,
    )
    out = dict(route)
    for key in ("summary", "rationale"):
        if isinstance(out.get(key), str):
            out[key] = sanitize_ai_prose(out[key])
    for key in ("cities", "stops", "city_stops"):
        if not isinstance(out.get(key), list):
            continue
        cleaned = []
        for stop in out[key]:
            if not isinstance(stop, dict):
                cleaned.append(stop)
                continue
            item = dict(stop)
            for field in ("city", "name", "reason", "rationale", "country"):
                if isinstance(item.get(field), str):
                    item[field] = sanitize_ai_prose(item[field])
            if isinstance(item.get("highlights"), list):
                item["highlights"] = [
                    sanitize_ai_prose(str(h)) if h is not None else h
                    for h in item["highlights"]
                ]
            cleaned.append(item)
        out[key] = cleaned
    return out
