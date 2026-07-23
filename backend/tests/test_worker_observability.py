"""Unit tests for worker / crew duration logging helpers."""

from __future__ import annotations

import logging

import pytest

from services.worker_observability import (
    WorkerTimer,
    log_crew_duration,
    log_worker_outcome,
)


def test_log_worker_outcome_includes_searchable_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="services.worker_observability"):
        log_worker_outcome(
            trip_id="t1",
            day_index=2,
            outcome="retry",
            duration_ms=42,
            retryable=True,
            error_code="agent_invoke_failed",
            error_type="TimeoutError",
        )
    assert "plan_next_day_worker" in caplog.text
    assert "outcome=retry" in caplog.text
    assert "trip_id=t1" in caplog.text
    assert "day_index=2" in caplog.text
    assert "duration_ms=42" in caplog.text
    assert "retryable=true" in caplog.text
    assert "error_code=agent_invoke_failed" in caplog.text


def test_worker_timer_non_negative() -> None:
    assert WorkerTimer().duration_ms() >= 0


def test_log_crew_duration(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="services.worker_observability"):
        log_crew_duration(
            operation="propose_cities",
            trip_id="t9",
            duration_ms=12,
            extra={"crew_mode": "fake"},
        )
    assert "propose_cities" in caplog.text
    assert "trip_id=t9" in caplog.text
    assert "crew_mode=fake" in caplog.text
