"""API request DTOs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class CreateTripRequest(BaseModel):
    origin: str = Field(min_length=1, max_length=200)
    destination: str = Field(min_length=1, max_length=200)
    destination_type: Literal["city", "country", "region"]
    start_date: str
    end_date: str
    preferences: str = Field(default="", max_length=2000)

    @field_validator("origin", "destination", "preferences", mode="before")
    @classmethod
    def strip_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class ConfirmCitiesRequest(BaseModel):
    destination_type: Literal["city", "country", "region"]
    cities: list[dict[str, Any]] = Field(min_length=1)
    rationale: str = ""
    total_nights: int = Field(default=0, ge=0)
    status: Literal["proposed", "confirmed"] = "confirmed"


class VisitedPlaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    city: str = Field(default="", max_length=200)
    note: str = Field(default="", max_length=500)

    @field_validator("name", "city", "note", mode="before")
    @classmethod
    def strip_visited(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class UpdateProfileRequest(BaseModel):
    display_name: str = Field(default="", max_length=200)
    preferences: str = Field(default="", max_length=2000)
    energy_level: int = Field(default=3, ge=1, le=5)
    interests: list[str] = Field(default_factory=list, max_length=40)
    visited_places: list[VisitedPlaceIn] = Field(default_factory=list, max_length=100)

    @field_validator("display_name", "preferences", mode="before")
    @classmethod
    def strip_profile_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("interests", mode="before")
    @classmethod
    def clean_interests(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip()[:80])
        return out[:40]
