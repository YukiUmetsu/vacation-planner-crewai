"""Domain models matching docs/DATA_MODEL.md."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from vacation_planner_models.keys import make_place_key


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
    order_in_day: int = Field(default=0, ge=0)
    place_key: str = ""

    @model_validator(mode="after")
    def fill_place_key(self) -> Place:
        if not self.place_key.strip():
            self.place_key = make_place_key(self.name, self.address)
        return self


class CityStop(BaseModel):
    city: str
    country: str = ""
    nights: int = Field(default=1, ge=0)
    arrival_day_index: int = Field(default=1, ge=1)
    departure_day_index: int = Field(default=1, ge=1)
    reason: str = ""
    highlights: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_day_window(self) -> CityStop:
        if self.departure_day_index < self.arrival_day_index:
            raise ValueError(
                "departure_day_index must be >= arrival_day_index "
                f"(got arrival={self.arrival_day_index}, departure={self.departure_day_index})"
            )
        return self


class CityRoute(BaseModel):
    destination_type: DestinationType
    cities: list[CityStop] = Field(min_length=1)
    rationale: str = ""
    total_nights: int = Field(default=0, ge=0)
    status: Literal["proposed", "confirmed"] = "proposed"

    @model_validator(mode="after")
    def sync_total_nights(self) -> CityRoute:
        nights_sum = sum(stop.nights for stop in self.cities)
        if self.total_nights == 0:
            self.total_nights = nights_sum
        elif self.total_nights != nights_sum:
            raise ValueError(
                f"total_nights ({self.total_nights}) must equal sum of city nights ({nights_sum})"
            )
        return self


class DayPlan(BaseModel):
    day_index: int = Field(ge=1, le=14)
    date: date
    theme: str = ""
    summary: str = ""
    overnight_city: str = Field(min_length=1)
    places: list[Place] = Field(min_length=3, max_length=6)

    @model_validator(mode="after")
    def assign_order_if_unset(self) -> DayPlan:
        if all(place.order_in_day == 0 for place in self.places):
            for index, place in enumerate(self.places, start=1):
                place.order_in_day = index
        return self


class Trip(BaseModel):
    trip_id: str = ""
    user_id: str = ""
    origin: str = ""
    destination: str = ""
    destination_type: DestinationType = DestinationType.city
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    day_count: int = Field(default=0, ge=0, le=14)
    next_day_index: int = Field(default=1, ge=1, le=14)
    status: str = "drafting"
    preferences: str = ""
    city_route: Optional[CityRoute] = None
    visited_place_keys: list[str] = Field(default_factory=list)
    prior_days_summary: str = ""
    days: list[DayPlan] = Field(default_factory=list)

    @field_validator("day_count")
    @classmethod
    def day_count_max(cls, value: int) -> int:
        if value > 14:
            raise ValueError("day_count must be <= 14")
        return value
