"""Amap (高德) place text search tool for mainland China research."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

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
    name: str = "Amap Place Search"
    description: str = (
        "Search mainland China points of interest via Amap (Gaode). "
        "Prefer this over generic web search when overnight_city / destination "
        "is in mainland China. Returns name, address, location, and id."
    )
    args_schema: Type[BaseModel] = AmapPlaceSearchInput

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
            return json.dumps(
                {
                    "error": "AMAP_WEB_KEY not configured",
                    "hint": "Fall back to web search; ask for street-level addresses.",
                }
            )
        params: dict[str, str] = {
            "key": key,
            "keywords": keywords.strip(),
            "offset": "8",
            "page": "1",
            "extensions": "all",
        }
        if city.strip():
            params["city"] = city.strip()
            params["citylimit"] = "true"
        url = f"{AMAP_PLACE_TEXT_URL}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=8.0) as resp:
                body: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return json.dumps({"error": f"HTTP {exc.code}", "keywords": keywords})
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc), "keywords": keywords})

        if str(body.get("status")) != "1":
            return json.dumps(
                {
                    "error": body.get("info") or "amap_error",
                    "keywords": keywords,
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
        return json.dumps(
            {"count": len(simplified), "pois": simplified},
            ensure_ascii=False,
        )
