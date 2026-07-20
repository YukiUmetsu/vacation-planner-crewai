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
