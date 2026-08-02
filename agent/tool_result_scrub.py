"""Scrub / cap tool JSON returned into CrewAI agent context (indirect injection)."""

from __future__ import annotations

import json
import re
from typing import Any

# Soft cap on tool observation size (chars) returned to the model.
MAX_TOOL_RESULT_CHARS = 6_000
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_HTML = re.compile(r"</?[a-zA-Z][^>]*>")


def scrub_text_field(value: Any, *, max_len: int = 240) -> str | None:
    if value is None:
        return None
    text = _HTML.sub("", _CONTROL.sub("", str(value)))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def scrub_amap_pois_payload(payload: dict[str, Any]) -> str:
    """Return compact JSON: structured POI fields only, size-capped."""
    pois_in = payload.get("pois") if isinstance(payload.get("pois"), list) else []
    pois_out: list[dict[str, Any]] = []
    for raw in pois_in[:8]:
        if not isinstance(raw, dict):
            continue
        pois_out.append(
            {
                "id": raw.get("id"),
                "name": scrub_text_field(raw.get("name"), max_len=120),
                "address": scrub_text_field(raw.get("address"), max_len=200),
                "city": scrub_text_field(raw.get("city"), max_len=80),
                "location": scrub_text_field(raw.get("location"), max_len=64),
                "type": scrub_text_field(raw.get("type"), max_len=120),
                "maps_url": scrub_text_field(raw.get("maps_url"), max_len=300),
            }
        )
    out: dict[str, Any] = {"count": len(pois_out), "pois": pois_out}
    if payload.get("error"):
        out["error"] = scrub_text_field(payload.get("error"), max_len=200)
    if payload.get("hint"):
        out["hint"] = scrub_text_field(payload.get("hint"), max_len=200)
    if payload.get("keywords"):
        out["keywords"] = scrub_text_field(payload.get("keywords"), max_len=120)
    encoded = json.dumps(out, ensure_ascii=False)
    if len(encoded) > MAX_TOOL_RESULT_CHARS:
        # Drop POIs from the end until under cap.
        while len(pois_out) > 1 and len(encoded) > MAX_TOOL_RESULT_CHARS:
            pois_out.pop()
            out["pois"] = pois_out
            out["count"] = len(pois_out)
            encoded = json.dumps(out, ensure_ascii=False)
        if len(encoded) > MAX_TOOL_RESULT_CHARS:
            encoded = encoded[: MAX_TOOL_RESULT_CHARS - 1] + "…"
    return encoded
