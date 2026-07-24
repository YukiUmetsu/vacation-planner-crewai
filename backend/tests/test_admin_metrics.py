"""Admin metrics route tests."""

from __future__ import annotations

import json
from typing import Any

from db import repository as repo
from handler import handler


def _event(
    method: str,
    path: str,
    *,
    user: str = "admin-sub",
    qs: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "requestContext": {"http": {"method": method, "path": path}},
        "rawPath": path,
        "headers": {"x-dev-user-sub": user},
        "queryStringParameters": qs,
    }


def test_metrics_forbidden_when_not_allowlisted(
    metrics_table: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("METRICS_ADMIN_SUBS", "other-admin")
    resp = handler(_event("GET", "/admin/metrics/runs", user="local-user"), None)
    assert resp["statusCode"] == 403
    body = json.loads(resp["body"])
    assert body["code"] == "forbidden"


def test_metrics_forbidden_when_allowlist_empty(
    metrics_table: Any, monkeypatch: Any
) -> None:
    monkeypatch.delenv("METRICS_ADMIN_SUBS", raising=False)
    resp = handler(_event("GET", "/admin/metrics/runs"), None)
    assert resp["statusCode"] == 403


def test_get_run_rejects_key_metacharacters(
    metrics_table: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("METRICS_ADMIN_SUBS", "admin-sub")
    resp = handler(
        _event(
            "GET",
            "/admin/metrics/runs/abc",
            qs={"started_at": "bad#value"},
        ),
        None,
    )
    assert resp["statusCode"] == 400
    assert json.loads(resp["body"])["code"] == "invalid_query"


def test_list_and_get_eval_runs(metrics_table: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("METRICS_ADMIN_SUBS", "admin-sub")
    started = "2026-07-19T15:00:00.000000Z"
    repo.put_eval_run(
        run_id="run-abc",
        started_at=started,
        experiment_key="expkey0123456789",
        dimensions={"preference_judge": "llm"},
        aggregates={"preference_relevance_score": 0.8},
        case_count=1,
        passed_count=1,
        updated_at=started,
        table=metrics_table,
    )
    repo.put_eval_case(
        run_id="run-abc",
        started_at=started,
        experiment_key="expkey0123456789",
        case_id="c1",
        passed=True,
        failures=[],
        metrics={"preference_relevance_score": 0.8},
        table=metrics_table,
    )

    list_resp = handler(_event("GET", "/admin/metrics/runs"), None)
    assert list_resp["statusCode"] == 200
    listed = json.loads(list_resp["body"])
    assert len(listed["runs"]) == 1
    assert listed["runs"][0]["run_id"] == "run-abc"

    filtered = handler(
        _event(
            "GET",
            "/admin/metrics/runs",
            qs={"experiment_key": "expkey0123456789"},
        ),
        None,
    )
    assert filtered["statusCode"] == 200
    assert len(json.loads(filtered["body"])["runs"]) == 1

    get_resp = handler(
        _event(
            "GET",
            "/admin/metrics/runs/run-abc",
            qs={"started_at": started},
        ),
        None,
    )
    assert get_resp["statusCode"] == 200
    detail = json.loads(get_resp["body"])
    assert detail["experiment_key"] == "expkey0123456789"
    assert len(detail["cases"]) == 1


def test_list_online_quality_and_product(
    metrics_table: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("METRICS_ADMIN_SUBS", "admin-sub")
    repo.put_online_quality_event(
        event_id="oq1",
        occurred_at="2026-07-19T17:00:00.000000Z",
        payload={"trip_id": "t9", "day_index": 2, "crew_name": "day_plan"},
        experiment_key="onlineexpkey00002",
        table=metrics_table,
    )
    repo.put_online_product_event(
        event_id="op1",
        occurred_at="2026-07-19T17:01:00.000000Z",
        event_name="time_to_accept",
        user_sub_hash="h1",
        payload={"ms": 1200},
        table=metrics_table,
    )

    q_resp = handler(
        _event("GET", "/admin/metrics/online", qs={"kind": "quality"}),
        None,
    )
    assert q_resp["statusCode"] == 200
    q_body = json.loads(q_resp["body"])
    assert q_body["kind"] == "quality"
    assert len(q_body["events"]) == 1

    p_resp = handler(
        _event(
            "GET",
            "/admin/metrics/online",
            qs={"kind": "product", "event_name": "time_to_accept"},
        ),
        None,
    )
    assert p_resp["statusCode"] == 200
    assert len(json.loads(p_resp["body"])["events"]) == 1

    bad = handler(
        _event("GET", "/admin/metrics/online", qs={"kind": "nope"}),
        None,
    )
    assert bad["statusCode"] == 400
