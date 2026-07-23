"""Bedrock AgentCore entrypoint — thin wrapper around crew kickoff."""

from __future__ import annotations

import logging
import os
from typing import Any

# Prefer ADOT / OpenTelemetry GenAI spans over CrewAI's built-in telemetry.
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")

from bedrock_agentcore import BedrockAgentCoreApp

from crew_kickoff import run_crew
from invoke_payload import PayloadError, parse_invoke_payload

app = BedrockAgentCoreApp()
logger = logging.getLogger(__name__)

# Safe for BFF → browser; never put paths / stack / SDK detail here.
_PUBLIC_CREW_FAILED = "Trip planning failed. Please try again."
_PUBLIC_CREW_NOT_FOUND = "Trip planning failed. Please try again."


def _error(message: str, code: str) -> dict[str, str]:
    return {"error": message, "code": code}


@app.entrypoint
def invoke(request: dict[str, Any]) -> dict[str, Any]:
    """AgentCore calls this with a JSON dict; always return a JSON object."""
    try:
        crew_name, inputs = parse_invoke_payload(request)
    except PayloadError as exc:
        return _error(str(exc), "invalid_payload")

    try:
        return run_crew(crew_name, inputs)
    except FileNotFoundError as exc:
        logger.exception("crew_not_found: %s", exc)
        return _error(_PUBLIC_CREW_NOT_FOUND, "crew_not_found")
    except ValueError as exc:
        return _error(str(exc), "invalid_crew")
    except Exception as exc:  # noqa: BLE001 — Runtime boundary; BFF maps envelope
        logger.exception("crew_failed: %s: %s", type(exc).__name__, exc)
        return _error(_PUBLIC_CREW_FAILED, "crew_failed")


if __name__ == "__main__":
    app.run()
