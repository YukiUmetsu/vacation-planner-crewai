"""Tests for crew envelope unwrap and hard quality policy."""

from __future__ import annotations

import pytest

from http_utils import ApiError
from services.crew_envelope import unwrap_crew_payload
from services.quality_policy import enforce_hard_quality, merge_quality_reports


def test_unwrap_legacy_bare_day_plan() -> None:
    bare = {"day_index": 1, "overnight_city": "Tokyo", "places": []}
    result, quality, invocation = unwrap_crew_payload(bare)
    assert result is bare
    assert quality is None
    assert invocation is None


def test_unwrap_envelope() -> None:
    day = {"day_index": 1, "overnight_city": "Tokyo", "places": []}
    payload = {
        "result": day,
        "quality": {
            "passes_relevance": True,
            "relevance_score": 4,
            "constraint_score": 5,
            "failure_tags": ["weak_reason"],
        },
        "invocation": {"crew_name": "day_plan", "prompt_version": "t"},
    }
    result, quality, invocation = unwrap_crew_payload(payload)
    assert result is day
    assert quality is not None
    assert quality["relevance_score"] == 4
    assert invocation is not None
    assert invocation["crew_name"] == "day_plan"


def test_soft_tags_do_not_block() -> None:
    enforce_hard_quality(
        {
            "passes_relevance": True,
            "failure_tags": [
                "preference_mismatch",
                "weak_reason",
                "energy_overload",
                "too_packed",
            ],
        }
    )


def test_scrub_bff_resolved_tags_drops_stale_crew_hard_tags() -> None:
    from services.quality_policy import scrub_bff_resolved_tags

    scrubbed = scrub_bff_resolved_tags(
        {
            "failure_tags": ["closed_place", "wrong_city", "energy_overload"],
            "relevance_score": 3,
        }
    )
    assert scrubbed is not None
    assert scrubbed["failure_tags"] == ["wrong_city"]
    assert scrubbed["passes_relevance"] is False
    enforce_hard_quality(
        scrub_bff_resolved_tags({"failure_tags": ["closed_place", "missing_meals"]})
    )


def test_hard_tags_block() -> None:
    with pytest.raises(ApiError) as exc:
        enforce_hard_quality({"failure_tags": ["duplicate_place", "weak_reason"]})
    assert exc.value.code == "place_duplicate"


def test_merge_quality_reports_unions_tags() -> None:
    merged = merge_quality_reports(
        {"failure_tags": ["weak_reason"], "relevance_score": 4},
        {"failure_tags": ["missing_meals"], "relevance_score": 2},
    )
    assert merged["failure_tags"] == ["weak_reason", "missing_meals"]
    assert merged["passes_relevance"] is False
    assert merged["relevance_score"] == 2
