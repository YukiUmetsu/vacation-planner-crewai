"""Drift check: OpenAPI paths/methods stay aligned with handler routes."""

from __future__ import annotations

from pathlib import Path

import yaml

OPENAPI_PATH = Path(__file__).resolve().parents[1] / "openapi.yaml"

# Expected (path, method) pairs from backend/src/handler.py (lowercase methods).
EXPECTED_OPERATIONS: set[tuple[str, str]] = {
    ("/profile", "get"),
    ("/profile", "put"),
    ("/events", "post"),
    ("/places/photo", "get"),
    ("/admin/metrics/runs", "get"),
    ("/admin/metrics/runs/{run_id}", "get"),
    ("/admin/metrics/online", "get"),
    ("/trips", "get"),
    ("/trips", "post"),
    ("/trips/{trip_id}", "get"),
    ("/trips/{trip_id}", "put"),
    ("/trips/{trip_id}", "delete"),
    ("/trips/{trip_id}/propose-cities", "post"),
    ("/trips/{trip_id}/cities", "put"),
    ("/trips/{trip_id}/plan-next-day", "post"),
    ("/trips/{trip_id}/days/{day_index}/suggest-place", "post"),
    ("/trips/{trip_id}/days/{day_index}", "delete"),
    ("/trips/{trip_id}/days/{day_index}/places/{place_index}", "delete"),
}


def _load_operations() -> set[tuple[str, str]]:
    doc = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    paths = doc.get("paths") or {}
    http_verbs = {"get", "put", "post", "delete", "patch", "head", "options"}
    found: set[tuple[str, str]] = set()
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method.lower() not in http_verbs:
                continue
            if not isinstance(op, dict):
                continue
            found.add((path, method.lower()))
    return found


def test_openapi_file_exists() -> None:
    assert OPENAPI_PATH.is_file(), f"missing {OPENAPI_PATH}"


def test_openapi_documents_handler_routes() -> None:
    found = _load_operations()
    missing = EXPECTED_OPERATIONS - found
    extra = found - EXPECTED_OPERATIONS
    assert not missing, f"OpenAPI missing operations: {sorted(missing)}"
    assert not extra, f"OpenAPI has unexpected operations: {sorted(extra)}"


def test_places_photo_documents_refresh() -> None:
    doc = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    params = doc["paths"]["/places/photo"]["get"]["parameters"]
    names = {p["name"] for p in params}
    assert "trip_id" in names
    assert "refresh" in names
    assert {"place_key", "place_id", "photo_name"} <= names
