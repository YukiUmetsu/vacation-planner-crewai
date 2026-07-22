"""Re-export shared models for CrewAI JSON ``python`` refs.

Unique module name so suggest_place can share a process with day_plan/city_route.
"""

from vacation_planner_models import (
    Place,
    PlaceCategory,
    make_place_key,
)

__all__ = [
    "Place",
    "PlaceCategory",
    "make_place_key",
]
