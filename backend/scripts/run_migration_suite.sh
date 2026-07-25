#!/usr/bin/env bash
# Domain-package regression suite (ADR 005) — contract + domain files.
#
# Usage (from backend/):
#   ./scripts/run_migration_suite.sh
#
# 1) Contract tests (@pytest.mark.migration) — import surface + TripService smokes
# 2) Domain regression files (no marker filter) — trip / plan / places / quality
#
# Exit non-zero if any test fails. Still run full `uv run pytest` before merging.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${BACKEND_DIR}"

echo "migration suite: (1/2) contract (@pytest.mark.migration)"
uv run pytest -q -m migration "$@"

echo "migration suite: (2/2) domain regression files"
uv run pytest -q \
  tests/test_trip_service.py \
  tests/test_plan_next_day_async.py \
  tests/test_remove_place_and_day.py \
  tests/test_day_plan_meals_and_gaps.py \
  tests/test_day_balance.py \
  tests/test_plan_day_retry.py \
  tests/test_place_quality.py \
  tests/test_quality_envelope.py \
  tests/test_places_enrich.py \
  tests/test_places_photo.py \
  tests/test_place_photo_cache.py \
  tests/test_place_image_fallback.py \
  tests/test_handler_routing.py \
  tests/test_crew_context_budget.py \
  tests/test_route_windows.py \
  tests/test_energy.py \
  tests/test_dedupe.py \
  "$@"

echo "migration suite: OK"
