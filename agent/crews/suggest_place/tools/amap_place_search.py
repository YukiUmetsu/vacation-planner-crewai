"""Amap (高德) place text search tool for mainland China research."""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# Crew tool files load via importlib; ensure agent/ root is on path for shared scrub.
_AGENT_ROOT = Path(__file__).resolve().parents[3]
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

from tool_result_scrub import scrub_amap_pois_payload  # noqa: E402

AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text"


class AmapPlaceSearchInput(BaseModel):
    keywords: str = Field(
        ...,
        description="Place name or keywords to search (Chinese or English).",
    )
    city: str = Field(
        default="",
        description="Optional city to bias results (e.g. Shanghai, 北京).",
    )


class AmapPlaceSearchTool(BaseTool):
    # Nova ToolUse is unreliable with spaces/hyphens in tool names.
    name: str = "amap_place_search"
    description: str = (
        "Search mainland China points of interest via Amap (Gaode). "
        "Prefer this over generic web search when overnight_city / destination "
        "is in mainland China. Returns name, address, location, and id."
    )
    # Concrete schema type (no __future__ annotations): CrewAI loads via importlib.
    args_schema: type[AmapPlaceSearchInput] = AmapPlaceSearchInput

    def _run(self, keywords: str, city: str = "") -> str:
        try:
            from runtime_secrets import ensure_amap_web_key

            key = ensure_amap_web_key()
        except ImportError:
            key = (
                os.getenv("AMAP_WEB_KEY", "").strip()
                or os.getenv("AMAP_KEY", "").strip()
            )
        if not key:
            return scrub_amap_pois_payload(
                {
                    "error": "AMAP_WEB_KEY not configured",
                    "hint": "Fall back to web search; ask for street-level addresses.",
                    "pois": [],
                }
            )
        params: dict[str, str] = {
            "key": key,
            "keywords": keywords.strip()[:120],
            "offset": "8",
            "page": "1",
            "extensions": "all",
        }
        if city.strip():
            params["city"] = city.strip()[:80]
            params["citylimit"] = "true"
        url = f"{AMAP_PLACE_TEXT_URL}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=8.0) as resp:
                body: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return scrub_amap_pois_payload(
                {"error": f"HTTP {exc.code}", "keywords": keywords, "pois": []}
            )
        except Exception as exc:  # noqa: BLE001
            return scrub_amap_pois_payload(
                {"error": str(exc), "keywords": keywords, "pois": []}
            )

        if str(body.get("status")) != "1":
            return scrub_amap_pois_payload(
                {
                    "error": body.get("info") or "amap_error",
                    "keywords": keywords,
                    "pois": [],
                }
            )
        pois = body.get("pois") if isinstance(body.get("pois"), list) else []
        simplified = []
        for raw in pois[:8]:
            if not isinstance(raw, dict):
                continue
            poi_id = str(raw.get("id") or "").strip()
            simplified.append(
                {
                    "id": f"amap:{poi_id}" if poi_id else None,
                    "name": raw.get("name"),
                    "address": raw.get("address"),
                    "city": raw.get("cityname"),
                    "location": raw.get("location"),
                    "type": raw.get("type"),
                    "maps_url": (
                        f"https://uri.amap.com/marker?position={raw.get('location')}"
                        f"&name={urllib.parse.quote(str(raw.get('name') or ''))}"
                        "&coordinate=gaode&callnative=0"
                        if raw.get("location")
                        else None
                    ),
                }
            )
        return scrub_amap_pois_payload({"pois": simplified})


AmapPlaceSearchTool.model_rebuild()
