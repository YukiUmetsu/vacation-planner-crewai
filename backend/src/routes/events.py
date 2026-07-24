"""Product analytics events (thin online metrics)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from http_utils import ApiError, parse_body
from services.worker_observability import log_product_event

ALLOWED_EVENTS = frozenset(
    {
        "proposal_accepted",
        "proposal_accepted_without_edit",
        "plan_regenerated",
        "place_deleted",
        "place_reordered",
        "suggestion_accepted",
        "manual_edit",
        "time_to_accept",
    }
)

# Per-event allowlisted payload keys (no free-form PII dumps).
_PAYLOAD_KEYS: dict[str, frozenset[str]] = {
    "proposal_accepted": frozenset({"source"}),
    "proposal_accepted_without_edit": frozenset({"source"}),
    "plan_regenerated": frozenset({"action"}),
    "place_deleted": frozenset({"place_index"}),
    "place_reordered": frozenset({"from_index", "to_index"}),
    "suggestion_accepted": frozenset({"source"}),
    "manual_edit": frozenset({"field"}),
    "time_to_accept": frozenset({"ms"}),
}

_MAX_PAYLOAD_VALUE_CHARS = 64
_MAX_PAYLOAD_KEYS = 4


class ProductEventRequest(BaseModel):
    event_name: str
    trip_id: str | None = None
    day_index: int | None = Field(default=None, ge=1, le=14)
    payload: dict[str, Any] = Field(default_factory=dict)
    client_ts: str | None = None


def _sanitize_payload(event_name: str, raw: dict[str, Any]) -> dict[str, Any]:
    allowed = _PAYLOAD_KEYS.get(event_name, frozenset())
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in allowed or len(out) >= _MAX_PAYLOAD_KEYS:
            continue
        if value is None or isinstance(value, bool):
            out[key] = value
        elif isinstance(value, (int, float)):
            out[key] = value
        else:
            text = str(value).strip()
            if text:
                out[key] = text[:_MAX_PAYLOAD_VALUE_CHARS]
    return out


def post_event(event: dict[str, Any], user_sub: str) -> dict[str, str]:
    body = parse_body(event)
    try:
        req = ProductEventRequest.model_validate(body)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(400, f"invalid event: {exc}", code="invalid_event") from exc
    name = req.event_name.strip()
    if name not in ALLOWED_EVENTS:
        raise ApiError(400, f"unknown event_name={name!r}", code="invalid_event")
    payload = _sanitize_payload(name, dict(req.payload))
    if req.client_ts:
        # ISO timestamp only; truncate.
        payload["client_ts"] = str(req.client_ts).strip()[:40]
    log_product_event(
        event_name=name,
        user_sub=user_sub,
        trip_id=req.trip_id,
        day_index=req.day_index,
        payload=payload,
    )
    return {"status": "ok"}
