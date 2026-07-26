"""Regression net for domain-package layout (ADR 005).

Locks the **public import surface** and a **TripService smoke path** so
refactors can be checked with the same command:

    ./scripts/run_migration_suite.sh
    # or: uv run pytest -m migration -q
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any

import pytest

from crews.fake_runner import FakeCrewRunner
from safety.gate import NoopSafetyGate
from trips.service import TripService

USER = "migration-suite-user"

_SRC_ROOT = Path(__file__).resolve().parents[1] / "src"


def _forbidden_imports(path: Path) -> list[str]:
    """Return human-readable import lines that violate ADR 005 boundaries."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(_SRC_ROOT)
    parts = rel.parts
    package = parts[0] if parts else ""
    is_trips_leaf = package == "trips" and path.name != "service.py"
    is_db = package == "db"

    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if is_trips_leaf and (
                    name == "trips.service" or name.startswith("trips.service.")
                ):
                    hits.append(f"{rel}: import {name}")
                if is_db and (name == "trips" or name.startswith("trips.")):
                    hits.append(f"{rel}: import {name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if is_trips_leaf and (
                mod == "trips.service" or mod.startswith("trips.service.")
            ):
                hits.append(f"{rel}: from {mod} import ...")
            if is_db and (mod == "trips" or mod.startswith("trips.")):
                hits.append(f"{rel}: from {mod} import ...")
            # ``from trips import service`` also pulls the service module.
            if is_trips_leaf and mod == "trips":
                for alias in node.names:
                    if alias.name == "service":
                        hits.append(f"{rel}: from trips import service")
    return hits


# Canonical domain import paths used by routes/, handler.py, and peers.
DOMAIN_IMPORT_PATHS: tuple[str, ...] = (
    "trips.service",
    "user_profile.service",
    "safety.gate",
    "safety.bedrock",
    "ops.plan_day_worker",
    "ops.worker_observability",
    "places.client",
    "places.enrich",
    "places.photo_cache",
    "places.image_fallback",
    "planning_quality.place_quality",
    "planning_quality.day_balance",
    "planning_quality.plan_day_retry",
    "planning_quality.quality_policy",
    "shared.energy",
    "planning_quality.dedupe",
    "shared.dates",
    "shared.route_windows",
    "crew_io.context_budget",
    "crew_io.envelope",
    "ops.secrets",
)

# Public methods routes / handler rely on today.
TRIP_SERVICE_PUBLIC_METHODS: tuple[str, ...] = (
    "create_trip",
    "update_trip",
    "list_trips",
    "get_trip",
    "delete_trip",
    "propose_cities",
    "confirm_cities",
    "plan_next_day",
    "start_plan_next_day",
    "execute_plan_next_day",
    "suggest_place",
    "remove_place",
    "delete_day",
)


@pytest.fixture()
def service(dynamodb_table: Any) -> TripService:
    return TripService(
        table=dynamodb_table,
        runner=FakeCrewRunner(),
        safety=NoopSafetyGate(),
    )


@pytest.mark.migration
def test_domain_import_paths_resolve() -> None:
    missing: list[str] = []
    for path in DOMAIN_IMPORT_PATHS:
        try:
            importlib.import_module(path)
        except Exception as exc:  # noqa: BLE001 — collect all failures
            missing.append(f"{path}: {type(exc).__name__}: {exc}")
    assert not missing, "broken domain imports:\n" + "\n".join(missing)


@pytest.mark.migration
def test_adr005_import_boundaries() -> None:
    """trips/* (except service.py) must not import trips.service; db/* must not import trips."""
    violations: list[str] = []
    for path in sorted(_SRC_ROOT.joinpath("trips").rglob("*.py")):
        if path.name == "service.py":
            continue
        violations.extend(_forbidden_imports(path))
    for path in sorted(_SRC_ROOT.joinpath("db").rglob("*.py")):
        violations.extend(_forbidden_imports(path))
    assert not violations, "ADR 005 import boundary violations:\n" + "\n".join(
        violations
    )


@pytest.mark.migration
def test_trip_service_public_methods_exist() -> None:
    missing = [name for name in TRIP_SERVICE_PUBLIC_METHODS if not hasattr(TripService, name)]
    assert not missing, f"TripService missing public methods: {missing}"


@pytest.mark.migration
def test_city_trip_plan_suggest_remove_smoke(service: TripService) -> None:
    """City destination: synthetic route → plan day → suggest → remove place."""
    created = service.create_trip(
        USER,
        {
            "origin": "Chicago",
            "destination": "Tokyo",
            "destination_type": "city",
            "start_date": "2026-09-01",
            "end_date": "2026-09-03",
            "preferences": "",
        },
    )
    trip_id = created["trip"]["trip_id"]
    assert created["trip"]["status"] == "routing_confirmed"
    assert created["route"]["status"] == "confirmed"
    assert created["route"]["cities"][0]["city"] == "Tokyo"

    planned = service.plan_next_day(USER, trip_id)
    assert planned["day"]["day_index"] == 1
    places_before = len(planned["day"]["places"])
    assert places_before >= 3

    # Leave headroom under the 7-stop cap for one suggest.
    while places_before > 6:
        service.remove_place(USER, trip_id, 1, places_before - 2)
        places_before -= 1

    suggested = service.suggest_place(USER, trip_id, 1)
    assert suggested["place"]["place_key"]
    assert len(suggested["day"]["places"]) == places_before + 1

    after_remove = service.remove_place(USER, trip_id, 1, 0)
    assert len(after_remove["day"]["places"]) == places_before

    bundle = service.get_trip(USER, trip_id)
    assert len(bundle["days"]) == 1
    assert bundle["route"] is not None


@pytest.mark.migration
def test_country_propose_confirm_plan_delete_day_smoke(service: TripService) -> None:
    """Country flow: propose → confirm → plan → delete day (cursor heal)."""
    created = service.create_trip(
        USER,
        {
            "origin": "Chicago",
            "destination": "Japan",
            "destination_type": "country",
            "start_date": "2026-09-01",
            "end_date": "2026-09-07",
            "preferences": "food",
        },
    )
    trip_id = created["trip"]["trip_id"]

    proposed = service.propose_cities(USER, trip_id)
    assert proposed["route"]["status"] == "proposed"

    confirmed = service.confirm_cities(
        USER,
        trip_id,
        {
            "destination_type": "country",
            "cities": proposed["route"]["cities"],
            "rationale": proposed["route"].get("rationale") or "",
            "total_nights": proposed["route"]["total_nights"],
            "status": "confirmed",
        },
    )
    assert confirmed["trip"]["status"] == "routing_confirmed"

    planned = service.plan_next_day(USER, trip_id)
    assert planned["day"]["day_index"] == 1
    assert planned["trip"]["next_day_index"] == 2

    deleted = service.delete_day(USER, trip_id, 1)
    assert deleted["trip"]["next_day_index"] == 1
    bundle = service.get_trip(USER, trip_id)
    assert bundle["days"] == []


@pytest.mark.migration
def test_list_and_delete_trip_smoke(service: TripService) -> None:
    created = service.create_trip(
        USER,
        {
            "origin": "A",
            "destination": "B",
            "destination_type": "city",
            "start_date": "2026-10-01",
            "end_date": "2026-10-02",
        },
    )
    trip_id = created["trip"]["trip_id"]
    listed = service.list_trips(USER)
    assert any(t["trip_id"] == trip_id for t in listed["trips"])

    service.delete_trip(USER, trip_id)
    listed_after = service.list_trips(USER)
    assert all(t["trip_id"] != trip_id for t in listed_after["trips"])
