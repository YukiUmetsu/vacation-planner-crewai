"""Key helpers for the dedicated metrics DynamoDB table (not the trip single-table).

See docs/DATA_MODEL.md — Offline eval metrics table.

Run and case sort keys use distinct prefixes so ``begins_with(RUN#)`` listing
never pulls case rows (DynamoDB ``Limit`` applies before filter).

Online quality/product events use ``ONLINE#*`` partitions so they never mix
with offline eval ``EVAL`` rows.
"""

from __future__ import annotations


def eval_pk() -> str:
    return "EVAL"


def run_sk(started_at_iso: str, run_id: str) -> str:
    return f"RUN#{started_at_iso}#{run_id}"


def case_sk(started_at_iso: str, run_id: str, case_id: str) -> str:
    """Case rows use CASE# so they are excluded from RUN# list queries."""
    return f"CASE#{started_at_iso}#{run_id}#{case_id}"


def case_sk_prefix(started_at_iso: str, run_id: str) -> str:
    return f"CASE#{started_at_iso}#{run_id}#"


def exp_gsi1_pk(experiment_key: str) -> str:
    return f"EXP#{experiment_key}"


def online_exp_gsi1_pk(experiment_key: str) -> str:
    """Separate from eval ``EXP#`` so GSI Limit is not shared across entity types."""
    return f"ONLINEEXP#{experiment_key}"


def run_gsi1_sk(started_at_iso: str, run_id: str) -> str:
    return f"RUN#{started_at_iso}#{run_id}"


def online_quality_pk() -> str:
    return "ONLINE#QUALITY"


def online_product_pk() -> str:
    return "ONLINE#PRODUCT"


def online_event_sk(occurred_at_iso: str, event_id: str) -> str:
    return f"TS#{occurred_at_iso}#{event_id}"


def evt_gsi1_pk(event_name: str) -> str:
    return f"EVT#{event_name}"
