#!/usr/bin/env bash
# Before / after services package migration — run the same suite both times.
#
# Usage (from backend/ or repo root):
#   ./scripts/run_migration_suite.sh
#   # or: bash backend/scripts/run_migration_suite.sh
#
# Exit non-zero if any test fails. Prefer this over full pytest while iterating
# on moves; still run `uv run pytest` before merging.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${BACKEND_DIR}"

echo "migration suite: contract + trip/plan/places/quality domain tests"
uv run pytest -q \
  -m migration \
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
