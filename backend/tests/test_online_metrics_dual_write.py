"""Online metrics dual-write soft-fail tests."""

from __future__ import annotations

from typing import Any

import db.repository as repo
from services import worker_observability as obs


def test_log_quality_still_emits_when_dynamo_fails(
    metrics_table: Any, monkeypatch: Any, caplog: Any
) -> None:
    def _boom(**_kwargs: Any) -> None:
        raise RuntimeError("ddb down")

    monkeypatch.setattr(repo, "put_online_quality_event", _boom)

    with caplog.at_level("INFO"):
        obs.log_quality_metrics(
            trip_id="t1",
            day_index=1,
            quality={"passes_relevance": True, "failure_tags": []},
            invocation={"crew_name": "day_plan", "prompt_version": "v"},
        )
    assert any("QUALITY_METRIC" in r.message for r in caplog.records)
    assert any("quality persist failed" in r.message for r in caplog.records)


def test_log_product_still_emits_when_dynamo_fails(
    metrics_table: Any, monkeypatch: Any, caplog: Any
) -> None:
    def _boom(**_kwargs: Any) -> None:
        raise RuntimeError("ddb down")

    monkeypatch.setattr(repo, "put_online_product_event", _boom)

    with caplog.at_level("INFO"):
        obs.log_product_event(event_name="proposal_accepted", user_sub="u1")
    assert any("PRODUCT_METRIC" in r.message for r in caplog.records)
    assert any("product persist failed" in r.message for r in caplog.records)


def test_log_quality_persists_to_metrics_table(metrics_table: Any) -> None:
    obs.log_quality_metrics(
        trip_id="t2",
        day_index=3,
        quality={
            "passes_relevance": True,
            "relevance_score": 4,
            "constraint_score": 5,
            "failure_tags": [],
        },
        invocation={
            "crew_name": "day_plan",
            "prompt_version": "2026-07-24.1",
            "prompt_hash": "phash",
            "model_id": "nova",
            "git_sha": "abc",
        },
        places_count=4,
    )
    events = repo.list_online_events(kind="quality", table=metrics_table)
    assert len(events) == 1
    assert events[0]["trip_id"] == "t2"
    assert events[0]["experiment_key"]


def test_log_product_persists_to_metrics_table(metrics_table: Any) -> None:
    obs.log_product_event(
        event_name="proposal_accepted",
        user_sub="user-xyz",
        trip_id="t3",
        day_index=1,
        payload={"source": "ui"},
    )
    events = repo.list_online_events(kind="product", table=metrics_table)
    assert len(events) == 1
    assert events[0]["event_name"] == "proposal_accepted"
    assert events[0]["trip_id"] == "t3"
    assert events[0]["payload"]["source"] == "ui"


def test_quality_payload_cannot_overwrite_keys(metrics_table: Any) -> None:
    from db.metrics_keys import online_event_sk, online_exp_gsi1_pk, online_quality_pk

    repo.put_online_quality_event(
        event_id="safe1",
        occurred_at="2026-07-19T18:00:00.000000Z",
        payload={
            "pk": "EVIL",
            "sk": "EVIL",
            "entity_type": "EVIL",
            "gsi1pk": "EXP#injected",
            "gsi1sk": "TS#injected",
            "experiment_key": "injectedkey!!!!!",
            "trip_id": "t-ok",
        },
        experiment_key="onlineexpkey00009",
        table=metrics_table,
    )
    events = repo.list_online_events(kind="quality", table=metrics_table)
    assert len(events) == 1
    assert events[0]["trip_id"] == "t-ok"
    assert events[0]["event_id"] == "safe1"
    assert events[0]["experiment_key"] == "onlineexpkey00009"

    raw = metrics_table.get_item(
        Key={
            "pk": online_quality_pk(),
            "sk": online_event_sk("2026-07-19T18:00:00.000000Z", "safe1"),
        }
    )["Item"]
    assert raw["gsi1pk"] == online_exp_gsi1_pk("onlineexpkey00009")
    assert raw["gsi1sk"] == online_event_sk("2026-07-19T18:00:00.000000Z", "safe1")

    # Without experiment_key, payload GSI fields must not land on the item.
    repo.put_online_quality_event(
        event_id="safe2",
        occurred_at="2026-07-19T18:01:00.000000Z",
        payload={
            "gsi1pk": "ONLINEEXP#sneaky",
            "gsi1sk": "TS#sneaky",
            "experiment_key": "sneaky",
            "trip_id": "t-bare",
        },
        experiment_key=None,
        table=metrics_table,
    )
    bare = metrics_table.get_item(
        Key={
            "pk": online_quality_pk(),
            "sk": online_event_sk("2026-07-19T18:01:00.000000Z", "safe2"),
        }
    )["Item"]
    assert "gsi1pk" not in bare
    assert "gsi1sk" not in bare
    assert "experiment_key" not in bare
