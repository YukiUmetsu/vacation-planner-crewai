"""Metrics repository tests (dedicated DynamoDB table)."""

from __future__ import annotations

from typing import Any

from db import repository as repo


def test_put_and_list_eval_runs(metrics_table: Any) -> None:
    repo.put_eval_run(
        run_id="r1",
        started_at="2026-07-19T12:00:00.000000Z",
        experiment_key="abcd1234efgh5678",
        dimensions={"live": False, "preference_judge": "heuristic"},
        aggregates={"schema_valid_rate": 1.0},
        case_count=2,
        passed_count=2,
        updated_at="2026-07-19T12:01:00.000000Z",
        table=metrics_table,
    )
    repo.put_eval_case(
        run_id="r1",
        started_at="2026-07-19T12:00:00.000000Z",
        experiment_key="abcd1234efgh5678",
        case_id="day_plan_example_shape",
        passed=True,
        failures=[],
        metrics={"schema_valid": 1.0},
        table=metrics_table,
    )

    runs = repo.list_eval_runs(table=metrics_table)
    assert len(runs) == 1
    assert runs[0]["run_id"] == "r1"
    assert runs[0]["experiment_key"] == "abcd1234efgh5678"

    by_exp = repo.list_eval_runs(
        experiment_key="abcd1234efgh5678", table=metrics_table
    )
    assert len(by_exp) == 1

    detail = repo.get_eval_run(
        run_id="r1",
        started_at="2026-07-19T12:00:00.000000Z",
        table=metrics_table,
    )
    assert detail is not None
    assert detail["case_count"] == 2
    assert len(detail["cases"]) == 1
    assert detail["cases"][0]["case_id"] == "day_plan_example_shape"


def test_list_runs_not_starved_by_case_rows(metrics_table: Any) -> None:
    """Case SKs must not compete with RUN# for DynamoDB Limit slots."""
    for i in range(3):
        started = f"2026-07-19T1{i}:00:00.000000Z"
        run_id = f"run{i}"
        repo.put_eval_run(
            run_id=run_id,
            started_at=started,
            experiment_key="sameexpkey000001",
            dimensions={"live": False},
            aggregates={"schema_valid_rate": 1.0},
            case_count=5,
            passed_count=5,
            updated_at=started,
            table=metrics_table,
        )
        for c in range(5):
            repo.put_eval_case(
                run_id=run_id,
                started_at=started,
                experiment_key="sameexpkey000001",
                case_id=f"case{c}",
                passed=True,
                failures=[],
                metrics={"schema_valid": 1.0},
                table=metrics_table,
            )

    listed = repo.list_eval_runs(limit=3, table=metrics_table)
    assert len(listed) == 3
    by_exp = repo.list_eval_runs(
        experiment_key="sameexpkey000001", limit=3, table=metrics_table
    )
    assert len(by_exp) == 3


def test_put_and_list_online_quality_and_product(metrics_table: Any) -> None:
    repo.put_online_quality_event(
        event_id="q1",
        occurred_at="2026-07-19T16:00:00.000000Z",
        payload={
            "trip_id": "t1",
            "day_index": 1,
            "passes_relevance": True,
            "crew_name": "day_plan",
            "prompt_version": "v1",
            "prompt_hash": "abc",
            "model_id": "m1",
            "git_sha": "deadbeef",
        },
        experiment_key="onlineexpkey00001",
        table=metrics_table,
    )
    repo.put_online_product_event(
        event_id="p1",
        occurred_at="2026-07-19T16:01:00.000000Z",
        event_name="proposal_accepted",
        user_sub_hash="hash1234",
        trip_id="t1",
        day_index=1,
        payload={"source": "ui"},
        table=metrics_table,
    )

    quality = repo.list_online_events(kind="quality", table=metrics_table)
    assert len(quality) == 1
    assert quality[0]["event_id"] == "q1"
    assert quality[0]["trip_id"] == "t1"

    by_exp = repo.list_online_events(
        kind="quality", experiment_key="onlineexpkey00001", table=metrics_table
    )
    assert len(by_exp) == 1

    product = repo.list_online_events(kind="product", table=metrics_table)
    assert len(product) == 1
    assert product[0]["event_name"] == "proposal_accepted"

    by_name = repo.list_online_events(
        kind="product", event_name="proposal_accepted", table=metrics_table
    )
    assert len(by_name) == 1
