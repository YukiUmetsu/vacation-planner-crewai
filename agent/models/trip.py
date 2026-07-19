"""Pydantic stubs matching docs/DATA_MODEL.md — fill in validators as crews adopt them."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PlaceCategory(str, Enum):
    museum = "museum"
    food = "food"
    park = "park"
    transit = "transit"
    lodging = "lodging"
    nightlife = "nightlife"
    shopping = "shopping"
    nature = "nature"
    other = "other"


class DestinationType(str, Enum):
    city = "city"
    country = "country"
    region = "region"


class Place(BaseModel):
    place_id: Optional[str] = None
    name: str
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    website_url: Optional[str] = None
    maps_url: Optional[str] = None
    category: PlaceCategory = PlaceCategory.other
    reason_to_visit: str = ""
    details: str = ""
    estimated_minutes: int = Field(default=60, gt=0)
    has_bathroom: Optional[bool] = None
    notes: Optional[str] = None
    order_in_day: int = 0
    place_key: str = ""


class CityStop(BaseModel):
    city: str
    country: str = ""
    nights: int = Field(default=1, ge=0)
    arrival_day_index: int = Field(default=1, ge=1)
    departure_day_index: int = Field(default=1, ge=1)
    reason: str = ""
    highlights: list[str] = Field(default_factory=list)


class CityRoute(BaseModel):
    destination_type: DestinationType
    cities: list[CityStop] = Field(default_factory=list)
    rationale: str = ""
    total_nights: int = 0
    status: str = "proposed"  # proposed | confirmed


class DayPlan(BaseModel):
    day_index: int = Field(ge=1, le=14)
    date: date
    theme: str = ""
    summary: str = ""
    overnight_city: str = ""
    places: list[Place] = Field(default_factory=list)


class Trip(BaseModel):
    trip_id: str = ""
    user_id: str = ""
    origin: str = ""
    destination: str = ""
    destination_type: DestinationType = DestinationType.city
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    day_count: int = 0
    next_day_index: int = 1
    status: str = "drafting"
    preferences: str = ""
    city_route: Optional[CityRoute] = None
    visited_place_keys: list[str] = Field(default_factory=list)
    prior_days_summary: str = ""
    days: list[DayPlan] = Field(default_factory=list)
