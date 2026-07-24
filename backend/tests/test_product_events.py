"""Tests for product event sanitization and stable user hashing."""

from __future__ import annotations

from routes.events import _sanitize_payload, post_event
from services.worker_observability import stable_user_sub_hash


def test_stable_user_sub_hash_is_deterministic() -> None:
    a = stable_user_sub_hash("user-123")
    b = stable_user_sub_hash("user-123")
    c = stable_user_sub_hash("user-other")
    assert a == b
    assert len(a) == 16
    assert a != c


def test_stable_user_sub_hash_uses_env_pepper(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("PRODUCT_METRICS_HASH_PEPPER", "pepper-a")
    a = stable_user_sub_hash("user-123")
    monkeypatch.setenv("PRODUCT_METRICS_HASH_PEPPER", "pepper-b")
    b = stable_user_sub_hash("user-123")
    assert a != b
    assert len(a) == 16


def test_sanitize_payload_strips_unknown_and_long_values() -> None:
    cleaned = _sanitize_payload(
        "place_deleted",
        {
            "place_index": 2,
            "email": "secret@example.com",
            "notes": "x" * 200,
        },
    )
    assert cleaned == {"place_index": 2}


def test_post_event_accepts_allowlisted(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen: dict = {}

    def _capture(**kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)

    monkeypatch.setattr("routes.events.log_product_event", _capture)
    out = post_event(
        {
            "body": (
                '{"event_name":"suggestion_accepted",'
                '"trip_id":"t1","day_index":1,'
                '"payload":{"source":"ui","ssn":"nope"}}'
            )
        },
        "user-abc",
    )
    assert out == {"status": "ok"}
    assert seen["payload"] == {"source": "ui"}
    assert seen["event_name"] == "suggestion_accepted"
