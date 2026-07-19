"""Run the vacation crew with Arize Phoenix tracing (local log UI).

Prerequisites (separate terminal):
  python -m phoenix.server.main serve
  open http://localhost:6006

Usage:
  python run_with_phoenix.py
  python run_with_phoenix.py --topic "Tokyo"
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from openinference.instrumentation.crewai import CrewAIInstrumentor
from phoenix.otel import register


def _disable_llm_streaming(crew) -> None:
    """Keep Bedrock native tool calls reliable (TUI forces stream=True)."""
    for agent in crew.agents:
        llm = getattr(agent, "llm", None)
        if llm is not None and hasattr(llm, "stream"):
            llm.stream = False


def main() -> None:
    parser = argparse.ArgumentParser(description="Run vacation_planner with Phoenix tracing")
    parser.add_argument("--topic", default="New York", help="Travel destination topic")
    parser.add_argument(
        "--phoenix-endpoint",
        default=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces"),
        help="Phoenix OTLP HTTP traces endpoint",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    load_dotenv(project_root / ".env", override=True)

    project_name = "vacation_planner"
    tracer_provider = register(
        endpoint=args.phoenix_endpoint,
        project_name=project_name,
        protocol="http/protobuf",
        auto_instrument=False,
        verbose=True,
    )
    CrewAIInstrumentor().instrument(skip_dep_check=True, tracer_provider=tracer_provider)

    # Lazy import after instrumentation so CrewAI spans are captured.
    from crewai.project import load_crew

    crew, default_inputs = load_crew(project_root / "crew.jsonc")
    _disable_llm_streaming(crew)

    result = crew.kickoff(inputs={**default_inputs, "topic": args.topic})
    print(result)

    # Ensure spans are flushed before the process exits.
    provider = tracer_provider
    if hasattr(provider, "force_flush"):
        provider.force_flush(timeout_millis=10_000)

    print(
        "\nPhoenix traces:\n"
        f"  1. Open http://localhost:6006\n"
        f"  2. Select project '{project_name}' (not 'default')\n"
        f"  3. Open the Traces tab and click the latest vacation_planner.kickoff run"
    )


if __name__ == "__main__":
    main()
