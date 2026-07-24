"""Runtime quality / relevance report and crew response envelope."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from vacation_planner_models.trip import DayPlan


class FailureTag(str, Enum):
    preference_mismatch = "preference_mismatch"
    excluded_category = "excluded_category"
    too_far = "too_far"
    too_packed = "too_packed"
    duplicate_place = "duplicate_place"
    wrong_city = "wrong_city"
    closed_place = "closed_place"
    weak_reason = "weak_reason"
    ungrounded_place = "ungrounded_place"
    missing_meals = "missing_meals"
    energy_overload = "energy_overload"
    food_only_day = "food_only_day"
    weak_day_balance = "weak_day_balance"


# Objective tags: BFF may block / fail the plan when present.
HARD_FAILURE_TAGS: frozenset[FailureTag] = frozenset(
    {
        FailureTag.duplicate_place,
        FailureTag.wrong_city,
        FailureTag.closed_place,
        FailureTag.excluded_category,
        FailureTag.missing_meals,
        FailureTag.food_only_day,
    }
)

SOFT_FAILURE_TAGS: frozenset[FailureTag] = frozenset(
    {
        FailureTag.preference_mismatch,
        FailureTag.too_far,
        FailureTag.weak_reason,
        FailureTag.ungrounded_place,
        FailureTag.weak_day_balance,
        FailureTag.too_packed,
        FailureTag.energy_overload,
    }
)

OUTPUT_SCHEMA_VERSION = "crew.envelope.v1"


class QualityReport(BaseModel):
    """Reviewer / BFF quality assessment for one crew result."""

    passes_relevance: bool = True
    relevance_score: int = Field(default=3, ge=1, le=5)
    constraint_score: int = Field(default=5, ge=1, le=5)
    failure_tags: list[FailureTag] = Field(default_factory=list)
    notes: str = ""

    def hard_tags(self) -> list[FailureTag]:
        return [t for t in self.failure_tags if t in HARD_FAILURE_TAGS]

    def soft_tags(self) -> list[FailureTag]:
        return [t for t in self.failure_tags if t in SOFT_FAILURE_TAGS]


class InvocationMeta(BaseModel):
    """Version / context metadata for one crew invocation (not persisted on DAY)."""

    crew_name: str
    prompt_version: str = ""
    prompt_hash: str = ""
    model_id: str = ""
    agent_runtime_arn: str = ""
    git_sha: str = ""
    input_context_chars: int = 0
    context_was_slimmed: bool = False
    output_schema_version: str = OUTPUT_SCHEMA_VERSION


class DayPlanWithQuality(BaseModel):
    """Final day_plan reviewer output: itinerary + structured quality check."""

    day_plan: DayPlan
    quality: QualityReport


class CrewEnvelope(BaseModel):
    """Wire format returned by AgentCore / local crew kickoff."""

    result: dict[str, Any]
    quality: Optional[QualityReport] = None
    invocation: InvocationMeta


# Note: result is typed as dict for wire flexibility (DayPlan | CityRoute | Place).
