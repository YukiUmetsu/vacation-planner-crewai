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
    keywords: str = Field(..., description="POI keywords / place name to search")
    city: str = Field(
        default="",
        description="Optional city or district to bias search (e.g. Shanghai)",
    )
    offset: int = Field(default=5, ge=1, le=25, description="Max results (1–25)")


class AmapPlaceSearchTool(BaseTool):
    name: str = "amap_place_search"
    description: str = (
        "Search mainland China points of interest via Amap (Gaode). "
        "Prefer this over generic web search when the overnight city is in mainland China."
    )
    args_schema: type[AmapPlaceSearchInput] = AmapPlaceSearchInput

    def _run(self, keywords: str, city: str = "", offset: int = 5) -> str:
        try:
            from runtime_secrets import ensure_amap_web_key

            key = ensure_amap_web_key()
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"amap_key_unavailable: {exc}"})

        params: dict[str, Any] = {
            "key": key,
            "keywords": keywords.strip(),
            "offset": str(max(1, min(int(offset or 5), 25))),
            "extensions": "all",
        }
        if city.strip():
            params["city"] = city.strip()
            params["citylimit"] = "true"

        url = f"{AMAP_PLACE_TEXT_URL}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=12) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return json.dumps({"error": f"http_{exc.code}"})
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

        if str(body.get("status")) != "1":
            return json.dumps(
                {
                    "error": body.get("info") or "amap_error",
                    "infocode": body.get("infocode"),
                }
            )

        pois = []
        for raw in body.get("pois") or []:
            if not isinstance(raw, dict):
                continue
            poi_id = str(raw.get("id") or "").strip()
            pois.append(
                {
                    "name": raw.get("name"),
                    "address": raw.get("address"),
                    "id": f"amap:{poi_id}" if poi_id else None,
                    "location": raw.get("location"),
                    "maps_url": (
                        f"https://uri.amap.com/marker?position={raw.get('location')}"
                        if raw.get("location")
                        else None
                    ),
                }
            )
        return json.dumps({"count": len(pois), "pois": pois}, ensure_ascii=False)


AmapPlaceSearchTool.model_rebuild()
