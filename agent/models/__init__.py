"""Domain models shared by crews — see docs/DATA_MODEL.md."""

from .trip import (
    CityRoute,
    CityStop,
    DayPlan,
    DestinationType,
    Place,
    PlaceCategory,
    Trip,
)

__all__ = [
    "CityRoute",
    "CityStop",
    "DayPlan",
    "DestinationType",
    "Place",
    "PlaceCategory",
    "Trip",
]
