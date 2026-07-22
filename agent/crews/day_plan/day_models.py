"""Re-export shared models for CrewAI JSON ``python`` refs.

Unique module name (not ``models``) so day_plan and city_route can share one
process without ``sys.modules`` clashes. Definitions live in
``vacation_planner_models``.
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
