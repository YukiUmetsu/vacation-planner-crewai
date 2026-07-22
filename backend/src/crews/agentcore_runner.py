"""CrewRunner that delegates to AgentCore Runtime."""
from __future__ import annotations
from typing import Any
from agentcore.client import invoke_agent

class AgentCoreRunner():
    def propose_cities(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Propose cities for a vacation."""
        return invoke_agent({
            "crew": "city_route",
            "inputs": inputs,
        })

    def plan_day(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Plan a day for a vacation."""
        return invoke_agent({
            "crew": "day_plan",
            "inputs": inputs,
        })