"""Run the day_plan crew with Arize Phoenix tracing.

Prerequisites (separate terminal):
  uv run python -m phoenix.server.main serve
  open http://localhost:6006

Usage:
  uv run python run_with_phoenix.py
  uv run python run_with_phoenix.py --overnight-city Tokyo --day-index 1 --date 2026-09-01
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openinference.instrumentation.crewai import CrewAIInstrumentor
from phoenix.otel import register


def _disable_llm_streaming(crew) -> None:
    for agent in crew.agents:
        llm = getattr(agent, "llm", None)
        if llm is not None and hasattr(llm, "stream"):
            llm.stream = False


def main() -> None:
    parser = argparse.ArgumentParser(description="Run day_plan crew with Phoenix tracing")
    parser.add_argument("--origin", default="San Francisco")
    parser.add_argument("--destination", default="Japan")
    parser.add_argument(
        "--destination-type",
        default="country",
        choices=["city", "country", "region"],
    )
    parser.add_argument("--day-index", type=int, default=1)
    parser.add_argument("--date", default="2026-09-01", help="YYYY-MM-DD")
    parser.add_argument("--overnight-city", default="Tokyo")
    parser.add_argument("--preferences", default="culture, food, moderate pace")
    parser.add_argument(
        "--already-visited",
        default="",
        help="Comma-separated place_keys to avoid",
    )
    parser.add_argument("--prior-days-summary", default="")
    parser.add_argument(
        "--city-route-json",
        default="",
        help="Optional confirmed CityRoute JSON string",
    )
    parser.add_argument(
        "--phoenix-endpoint",
        default=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces"),
    )
    args = parser.parse_args()

    if args.day_index < 1 or args.day_index > 14:
        raise SystemExit("day-index must be 1..14")
    datetime.strptime(args.date, "%Y-%m-%d")

    project_root = Path(__file__).resolve().parent
    agent_root = project_root.parents[1]
    load_dotenv(agent_root / ".env", override=True)
    (project_root / "logs").mkdir(exist_ok=True)
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")

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
    from day_models import DayPlan

    crew, default_inputs = load_crew(project_root / "crew.jsonc")
    _disable_llm_streaming(crew)

    inputs = {
        **default_inputs,
        "origin": args.origin,
        "destination": args.destination,
        "destination_type": args.destination_type,
        "day_index": str(args.day_index),
        "date": args.date,
        "overnight_city": args.overnight_city,
        "preferences": args.preferences,
        "already_visited": args.already_visited,
        "prior_days_summary": args.prior_days_summary,
        "city_route_json": args.city_route_json,
    }
    result = crew.kickoff(inputs=inputs)

    pydantic_out = getattr(result, "pydantic", None)
    if pydantic_out is not None:
        plan = (
            pydantic_out
            if isinstance(pydantic_out, DayPlan)
            else DayPlan.model_validate(pydantic_out)
        )
        print(plan.model_dump_json(indent=2))
    else:
        print(result)
        raise SystemExit("Failure: kickoff did not return output_pydantic DayPlan")

    if hasattr(tracer_provider, "force_flush"):
        tracer_provider.force_flush(timeout_millis=10_000)

    print(
        "\nPhoenix traces:\n"
        f"  1. Open http://localhost:6006\n"
        f"  2. Select project '{project_name}' (not 'default')\n"
        f"  3. Open Traces for the latest day_plan.kickoff run"
    )


if __name__ == "__main__":
    main()
