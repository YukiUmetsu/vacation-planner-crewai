"""Shared domain models for Vacation Planner crews and APIs."""

from vacation_planner_models.keys import make_place_key, normalize_place_text
from vacation_planner_models.prompt_meta import PROMPT_VERSIONS, prompt_hash_for_crew
from vacation_planner_models.quality import (
    HARD_FAILURE_TAGS,
    OUTPUT_SCHEMA_VERSION,
    SOFT_FAILURE_TAGS,
    CrewEnvelope,
    DayPlanWithQuality,
    FailureTag,
    InvocationMeta,
    QualityReport,
)
from vacation_planner_models.trip import (
    CityRoute,
    CityStop,
    DayPlan,
    DestinationType,
    Place,
    PlaceCategory,
    Trip,
)

__all__ = [
    "HARD_FAILURE_TAGS",
    "OUTPUT_SCHEMA_VERSION",
    "PROMPT_VERSIONS",
    "SOFT_FAILURE_TAGS",
    "CityRoute",
    "CityStop",
    "CrewEnvelope",
    "DayPlan",
    "DayPlanWithQuality",
    "DestinationType",
    "FailureTag",
    "InvocationMeta",
    "Place",
    "PlaceCategory",
    "QualityReport",
    "Trip",
    "make_place_key",
    "normalize_place_text",
    "prompt_hash_for_crew",
]
