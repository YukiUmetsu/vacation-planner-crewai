"""Run the city_route crew with Arize Phoenix tracing.

Prerequisites (separate terminal):
  uv run python -m phoenix.server.main serve
  open http://localhost:6006

Usage:
  uv run python run_with_phoenix.py
  uv run python run_with_phoenix.py --destination Japan --day-count 10
"""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta
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


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _day_count(start: date, end: date) -> int:
    return (end - start).days + 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run city_route crew with Phoenix tracing")
    parser.add_argument("--origin", default="San Francisco")
    parser.add_argument("--destination", default="Japan")
    parser.add_argument(
        "--destination-type",
        default="country",
        choices=["city", "country", "region"],
    )
    parser.add_argument("--start-date", default="2026-09-01", help="YYYY-MM-DD")
    parser.add_argument("--end-date", default="2026-09-10", help="YYYY-MM-DD")
    parser.add_argument(
        "--day-count",
        type=int,
        default=None,
        help="Inclusive day count (defaults from start/end dates)",
    )
    parser.add_argument(
        "--preferences",
        default="mix of big cities and culture; moderate pace",
    )
    parser.add_argument(
        "--phoenix-endpoint",
        default=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces"),
    )
    args = parser.parse_args()

    start = _parse_date(args.start_date)
    end = _parse_date(args.end_date)
    if end < start:
        raise SystemExit("end-date must be on or after start-date")
    day_count = args.day_count if args.day_count is not None else _day_count(start, end)
    if day_count < 1 or day_count > 14:
        raise SystemExit("day_count must be between 1 and 14")
    if day_count != _day_count(start, end):
        # Keep dates authoritative if caller passes a mismatched day_count.
        end = start + timedelta(days=day_count - 1)

    project_root = Path(__file__).resolve().parent
    agent_root = project_root.parents[1]  # agent/
    load_dotenv(agent_root / ".env", override=True)
    (project_root / "logs").mkdir(exist_ok=True)

    project_name = "vacation_planner"
    tracer_provider = register(
        endpoint=args.phoenix_endpoint,
        project_name=project_name,
        protocol="http/protobuf",
        auto_instrument=False,
        verbose=True,
    )
    CrewAIInstrumentor().instrument(skip_dep_check=True, tracer_provider=tracer_provider)

    from crewai.project import load_crew

    crew, default_inputs = load_crew(project_root / "crew.jsonc")
    _disable_llm_streaming(crew)

    inputs = {
        **default_inputs,
        "origin": args.origin,
        "destination": args.destination,
        "destination_type": args.destination_type,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "day_count": str(day_count),
        "preferences": args.preferences,
    }
    result = crew.kickoff(inputs=inputs)

    pydantic_out = getattr(result, "pydantic", None)
    if pydantic_out is not None:
        print(pydantic_out.model_dump_json(indent=2))
    else:
        print(result)

    if hasattr(tracer_provider, "force_flush"):
        tracer_provider.force_flush(timeout_millis=10_000)

    print(
        "\nPhoenix traces:\n"
        f"  1. Open http://localhost:6006\n"
        f"  2. Select project '{project_name}' (not 'default')\n"
        f"  3. Open Traces for the latest city_route.kickoff run"
    )


if __name__ == "__main__":
    main()
