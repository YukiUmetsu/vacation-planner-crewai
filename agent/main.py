"""Bedrock AgentCore entrypoint — thin wrapper around crew kickoff."""

from __future__ import annotations

from typing import Any

from bedrock_agentcore import BedrockAgentCoreApp

from crew_kickoff import run_crew
from invoke_payload import PayloadError, parse_invoke_payload

app = BedrockAgentCoreApp()


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
        return _error(str(exc), "crew_not_found")
    except ValueError as exc:
        return _error(str(exc), "invalid_crew")
    except Exception as exc:  # noqa: BLE001 — Runtime boundary; BFF maps envelope
        return _error(f"{type(exc).__name__}: {exc}", "crew_failed")


if __name__ == "__main__":
    app.run()
