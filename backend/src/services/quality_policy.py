"""Merge crew QualityReport with BFF policy: block hard tags, log soft tags."""

from __future__ import annotations

from typing import Any

from http_utils import ApiError

# Keep in sync with vacation_planner_models.quality.HARD_FAILURE_TAGS / SOFT_*.
HARD_FAILURE_TAGS = frozenset(
    {
        "duplicate_place",
        "wrong_city",
        "closed_place",
        "excluded_category",
        "missing_meals",
        "food_only_day",
    }
)
SOFT_FAILURE_TAGS = frozenset(
    {
        "preference_mismatch",
        "too_far",
        "weak_reason",
        "ungrounded_place",
        "weak_day_balance",
        "too_packed",
        "energy_overload",
    }
)

_TAG_TO_CODE: dict[str, str] = {
    "duplicate_place": "place_duplicate",
    "wrong_city": "wrong_city",
    "closed_place": "place_closed",
    "too_packed": "energy_overload",
    "energy_overload": "energy_overload",
    "excluded_category": "excluded_category",
    "missing_meals": "missing_meals",
    "food_only_day": "food_only_day",
}

# After BFF closed/visited/meal/balance gates pass, crew reviewer tags for the
# same issues are stale and must not hard-fail (or burn a wasted "success").
BFF_RESOLVED_TAGS: frozenset[str] = frozenset(
    {
        "closed_place",
        "duplicate_place",
        "missing_meals",
        "food_only_day",
        "too_packed",
        "energy_overload",
    }
)


def normalize_failure_tags(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        tag = str(item or "").strip()
        if tag and tag not in out:
            out.append(tag)
    return out


def scrub_bff_resolved_tags(quality: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop crew tags already enforced by BFF deterministic gates."""
    if not quality:
        return quality
    tags = [
        t
        for t in normalize_failure_tags(quality.get("failure_tags"))
        if t not in BFF_RESOLVED_TAGS
    ]
    hard, _soft = split_tags(tags)
    return {
        **quality,
        "failure_tags": tags,
        "passes_relevance": len(hard) == 0,
    }


def split_tags(tags: list[str]) -> tuple[list[str], list[str]]:
    hard = [t for t in tags if t in HARD_FAILURE_TAGS]
    soft = [t for t in tags if t in SOFT_FAILURE_TAGS]
    return hard, soft


def merge_quality_reports(
    *reports: dict[str, Any] | None,
) -> dict[str, Any]:
    """Union failure_tags; min scores; passes_relevance false if any hard tag."""
    tags: list[str] = []
    relevance_scores: list[int] = []
    constraint_scores: list[int] = []
    notes: list[str] = []
    for report in reports:
        if not report:
            continue
        tags.extend(normalize_failure_tags(report.get("failure_tags")))
        try:
            relevance_scores.append(int(report.get("relevance_score") or 3))
        except (TypeError, ValueError):
            relevance_scores.append(3)
        try:
            constraint_scores.append(int(report.get("constraint_score") or 5))
        except (TypeError, ValueError):
            constraint_scores.append(5)
        note = str(report.get("notes") or "").strip()
        if note:
            notes.append(note)

    deduped: list[str] = []
    for tag in tags:
        if tag not in deduped:
            deduped.append(tag)
    hard, _soft = split_tags(deduped)
    return {
        "passes_relevance": len(hard) == 0,
        "relevance_score": min(relevance_scores) if relevance_scores else 3,
        "constraint_score": min(constraint_scores) if constraint_scores else 5,
        "failure_tags": deduped,
        "notes": " | ".join(notes),
    }


def enforce_hard_quality(quality: dict[str, Any] | None) -> None:
    """Raise ApiError when objective failure tags are present."""
    if not quality:
        return
    tags = normalize_failure_tags(quality.get("failure_tags"))
    hard, _ = split_tags(tags)
    if not hard:
        return
    primary = hard[0]
    code = _TAG_TO_CODE.get(primary, "quality_hard_fail")
    raise ApiError(
        422,
        "day plan failed objective quality checks "
        f"(tags: {', '.join(hard)})",
        code=code,
    )
