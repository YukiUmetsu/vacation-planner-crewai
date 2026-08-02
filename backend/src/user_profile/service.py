"""User profile persistence (prefs, energy, interests, visited places, role/plan)."""

from __future__ import annotations

from typing import Any

from db import repository as repo
from db.protocols import DynamoDBTable
from http_utils import ApiError, public_item
from limits.admin import (
    admin_emails,
    metrics_admin_subs,
    normalize_plan,
    normalize_role,
)
from models.api import UpdateProfileRequest
from shared.energy import clamp_energy_level, max_minutes_for_energy
from safety.gate import SafetyGate, check_texts, get_safety_gate


def _default_profile(user_sub: str) -> dict[str, Any]:
    return {
        "user_id": user_sub,
        "display_name": "",
        "preferences": "",
        "energy_level": 3,
        "interests": [],
        "visited_places": [],
        "suggest_include_breakfast": False,
        "role": "user",
        "plan": "free",
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
        "suggest_include_breakfast": bool(public.get("suggest_include_breakfast")),
        "role": normalize_role(public.get("role")),
        "plan": normalize_plan(public.get("plan")),
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

    def get_profile(self, user_sub: str, *, email: str | None = None) -> dict[str, Any]:
        """Return profile, ensuring defaults and admin bootstrap from ADMIN_EMAILS."""
        item = repo.get_profile(user_sub=user_sub, table=self._table)
        if not item:
            public = {**_default_profile(user_sub), "persisted": False}
        else:
            public = {**_enrich(public_item(item)), "persisted": True}

        mail = (email or "").strip().lower()
        should_promote = False
        if mail and mail in admin_emails():
            should_promote = True
        elif user_sub and user_sub in metrics_admin_subs():
            should_promote = True
        if should_promote and normalize_role(public.get("role")) != "admin":
            item = repo.promote_profile_admin(user_sub=user_sub, table=self._table)
            public = {**_enrich(public_item(item)), "persisted": True}

        return public

    def put_profile(self, user_sub: str, body: dict[str, Any], *, email: str | None = None) -> dict[str, Any]:
        # Strip client attempts to set server-owned fields.
        body = {k: v for k, v in body.items() if k not in {"role", "plan", "user_id"}}
        try:
            req = UpdateProfileRequest.model_validate(body)
        except Exception as exc:  # noqa: BLE001 — pydantic ValidationError
            raise ApiError(400, f"invalid profile: {exc}", code="validation_error") from exc

        fields: dict[str, str | None] = {
            "preferences": req.preferences,
            "display_name": req.display_name,
        }
        for index, interest in enumerate(req.interests):
            fields[f"interests[{index}]"] = interest
        check_texts(self.safety, fields)

        # Ensure bootstrap before overwrite so admin role is preserved via put_profile merge.
        self.get_profile(user_sub, email=email)

        visited = [vp.model_dump() for vp in req.visited_places]
        item = repo.put_profile(
            user_sub=user_sub,
            display_name=req.display_name,
            preferences=req.preferences,
            energy_level=clamp_energy_level(req.energy_level),
            interests=req.interests,
            visited_places=visited,
            suggest_include_breakfast=bool(req.suggest_include_breakfast),
            table=self._table,
        )
        return {**_enrich(public_item(item)), "persisted": True}
