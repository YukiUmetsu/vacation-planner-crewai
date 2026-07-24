"""Persistence for trips / routes / days / profiles / eval metrics.

Public API stays on ``db.repository`` so callers keep ``from db import repository as repo``.
Implementation is split by concern:

- ``common`` — errors, table helpers, sanitizer re-exports
- ``trips`` — trip meta, routes, bundles, visited keys
- ``planning`` — plan-next-day locks and itinerary cursors
- ``days`` — day rows and suggest-place writes
- ``profile`` — traveler profile
- ``metrics`` — offline eval + online quality/product (dedicated metrics DynamoDB table)
"""

from __future__ import annotations

from db.repository.common import (
    ConcurrentModificationError,
    PersistenceError,
    prepare_dynamo_item,
    prepare_dynamo_value,
    _assert_no_floats,
    _dynamo_safe,
    _strip_nones,
)
from db.repository.days import (
    delete_day,
    get_day,
    persist_planned_day,
    persist_suggested_place,
    put_day,
    put_day_if_absent,
    replace_day_places,
)
from db.repository.planning import (
    PLANNING_STALE_SECONDS,
    apply_itinerary_edit,
    claim_next_day_slot,
    claim_planning_in_progress,
    clear_stale_planning_claim,
    complete_planning_after_day_write,
    fail_planning_in_progress,
    rollback_next_day_slot,
)
from db.repository.profile import get_profile, put_profile
from db.repository.metrics import (
    get_eval_run,
    list_eval_runs,
    list_online_events,
    put_eval_case,
    put_eval_run,
    put_online_product_event,
    put_online_quality_event,
)
from db.repository.trips import (
    append_visited_place_key,
    begin_trip_delete,
    delete_route,
    delete_trip_bundle,
    get_trip_bundle,
    get_trip_by_id_via_gsi,
    get_trip_meta,
    list_trip_meta_for_user,
    prune_visited_place_keys,
    put_route,
    put_trip,
    update_trip,
)

__all__ = [
    "ConcurrentModificationError",
    "PersistenceError",
    "PLANNING_STALE_SECONDS",
    "prepare_dynamo_item",
    "prepare_dynamo_value",
    "_strip_nones",
    "_assert_no_floats",
    "_dynamo_safe",
    "put_trip",
    "put_route",
    "delete_route",
    "put_day",
    "list_trip_meta_for_user",
    "get_trip_bundle",
    "delete_trip_bundle",
    "get_trip_by_id_via_gsi",
    "get_trip_meta",
    "update_trip",
    "claim_next_day_slot",
    "clear_stale_planning_claim",
    "claim_planning_in_progress",
    "complete_planning_after_day_write",
    "fail_planning_in_progress",
    "rollback_next_day_slot",
    "put_day_if_absent",
    "get_day",
    "replace_day_places",
    "delete_day",
    "apply_itinerary_edit",
    "persist_planned_day",
    "persist_suggested_place",
    "append_visited_place_key",
    "begin_trip_delete",
    "prune_visited_place_keys",
    "get_profile",
    "put_profile",
    "put_eval_run",
    "put_eval_case",
    "list_eval_runs",
    "get_eval_run",
    "put_online_quality_event",
    "put_online_product_event",
    "list_online_events",
]
