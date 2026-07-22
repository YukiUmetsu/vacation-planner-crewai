"""User profile persistence (prefs, energy, interests, visited places)."""

from __future__ import annotations

from typing import Any

from db import repository as repo
from db.protocols import DynamoDBTable
from http_utils import ApiError, public_item
from models.api import UpdateProfileRequest
from services.energy import clamp_energy_level, max_minutes_for_energy
from services.safety import SafetyGate, get_safety_gate


def _default_profile(user_sub: str) -> dict[str, Any]:
    return {
        "user_id": user_sub,
        "display_name": "",
        "preferences": "",
        "energy_level": 3,
        "interests": [],
        "visited_places": [],
        "max_comfortable_minutes": max_minutes_for_energy(3),
    }


def _enrich(public: dict[str, Any]) -> dict[str, Any]:
    level = clamp_energy_level(public.get("energy_level"))
    return {
        **public,
        "energy_level": level,
        "max_comfortable_minutes": max_minutes_for_energy(level),
        "interests": list(public.get("interests") or []),
        "visited_places": list(public.get("visited_places") or []),
    }


class ProfileService:
    def __init__(
        self,
        *,
        table: DynamoDBTable | None = None,
        safety: SafetyGate | None = None,
    ) -> None:
        self._table = table
        self._safety = safety

    @property
    def safety(self) -> SafetyGate:
        if self._safety is None:
            self._safety = get_safety_gate()
        return self._safety

    def get_profile(self, user_sub: str) -> dict[str, Any]:
        """Return the stored profile, or blank defaults for planning context."""
        item = repo.get_profile(user_sub=user_sub, table=self._table)
        if not item:
            return _default_profile(user_sub)
        return _enrich(public_item(item))

    def get_persisted_profile(self, user_sub: str) -> dict[str, Any]:
        """Return a saved profile only; 404 when nothing has been PUT yet."""
        item = repo.get_profile(user_sub=user_sub, table=self._table)
        if not item:
            raise ApiError(404, "profile not found", code="not_found")
        return _enrich(public_item(item))

    def put_profile(self, user_sub: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            req = UpdateProfileRequest.model_validate(body)
        except Exception as exc:  # noqa: BLE001 — pydantic ValidationError
            raise ApiError(400, f"invalid profile: {exc}", code="validation_error") from exc

        self.safety.check_text(req.preferences, source="preferences")
        self.safety.check_text(req.display_name, source="display_name")
        for interest in req.interests:
            self.safety.check_text(interest, source="interests")

        visited = [vp.model_dump() for vp in req.visited_places]
        item = repo.put_profile(
            user_sub=user_sub,
            display_name=req.display_name,
            preferences=req.preferences,
            energy_level=clamp_energy_level(req.energy_level),
            interests=req.interests,
            visited_places=visited,
            table=self._table,
        )
        return _enrich(public_item(item))
