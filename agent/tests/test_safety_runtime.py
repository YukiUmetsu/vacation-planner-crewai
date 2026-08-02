"""Unit tests for tool_result_scrub + invoke_payload allowlist."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from invoke_payload import PayloadError, allowed_crews, parse_invoke_payload  # noqa: E402
from tool_result_scrub import scrub_amap_pois_payload  # noqa: E402


def test_scrub_amap_caps_and_strips_html() -> None:
    raw = scrub_amap_pois_payload(
        {
            "pois": [
                {
                    "id": "amap:1",
                    "name": "<b>Temple</b>",
                    "address": "1 Main\x00St",
                    "city": "Shanghai",
                    "location": "121,31",
                    "type": "Scenic",
                    "maps_url": "https://uri.amap.com/marker?position=1",
                }
            ]
        }
    )
    data = json.loads(raw)
    assert data["count"] == 1
    assert "<b>" not in data["pois"][0]["name"]
    assert "\x00" not in (data["pois"][0]["address"] or "")


def test_parse_rejects_day_plan_single_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ALLOW_EVAL_CREWS", raising=False)
    assert "day_plan_single" not in allowed_crews()
    with pytest.raises(PayloadError):
        parse_invoke_payload({"crew": "day_plan_single", "inputs": {}})


def test_parse_allows_day_plan_single_when_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_EVAL_CREWS", "1")
    assert "day_plan_single" in allowed_crews()
    crew, inputs = parse_invoke_payload(
        {"crew": "day_plan_single", "inputs": {"x": "1"}}
    )
    assert crew == "day_plan_single"
    assert inputs["x"] == "1"


def test_parse_allows_prod_crews(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALLOW_EVAL_CREWS", raising=False)
    crew, _ = parse_invoke_payload({"crew": "day_plan", "inputs": {}})
    assert crew == "day_plan"
