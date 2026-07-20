"""Re-export shared models for CrewAI JSON `python` refs.

CrewAI only resolves classes under this crew's project root. The real
definitions live in the `vacation-planner-models` package.
"""

from vacation_planner_models import (
    CityRoute,
    CityStop,
    DayPlan,
    DestinationType,
    Place,
    PlaceCategory,
    Trip,
    make_place_key,
)

__all__ = [
    "CityRoute",
    "CityStop",
    "DayPlan",
    "DestinationType",
    "Place",
    "PlaceCategory",
    "Trip",
    "make_place_key",
]
