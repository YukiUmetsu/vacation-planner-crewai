"""Smoke-test day_plan: kickoff crew and assert a valid DayPlan.

Requires agent/.env (SERPER_API_KEY + AWS creds).

Usage:
  uv run python smoke_test.py
  uv run python smoke_test.py --overnight-city Tokyo --day-index 1 --date 2026-09-01
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


def _extract_day_plan(result):  # noqa: ANN001
    from day_models import DayPlan

    pydantic_out = getattr(result, "pydantic", None)
    if pydantic_out is not None:
        if isinstance(pydantic_out, DayPlan):
            return pydantic_out
        return DayPlan.model_validate(pydantic_out)

    raw = getattr(result, "raw", None) or str(result)
    if isinstance(raw, dict):
        return DayPlan.model_validate(raw)
    try:
        return DayPlan.model_validate_json(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return DayPlan.model_validate_json(raw[start : end + 1])
        raise


def _assert_day_plan(plan, *, day_index: int, date_str: str, overnight_city: str) -> None:
    assert plan.day_index == day_index
    assert plan.date.isoformat() == date_str
    assert plan.overnight_city == overnight_city
    assert 3 <= len(plan.places) <= 6
    keys = [p.place_key for p in plan.places]
    assert all(keys), "every place must have place_key"
    assert len(keys) == len(set(keys)), "place_key values must be unique within the day"


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test day_plan → DayPlan")
    parser.add_argument("--origin", default="San Francisco")
    parser.add_argument("--destination", default="Japan")
    parser.add_argument(
        "--destination-type",
        default="country",
        choices=["city", "country", "region"],
    )
    parser.add_argument("--day-index", type=int, default=1)
    parser.add_argument("--date", default="2026-09-01")
    parser.add_argument("--overnight-city", default="Tokyo")
    parser.add_argument("--preferences", default="culture, food, moderate pace")
    parser.add_argument("--already-visited", default="")
    parser.add_argument("--prior-days-summary", default="")
    parser.add_argument("--city-route-json", default="")
    parser.add_argument(
        "--phoenix-endpoint",
        default=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces"),
    )
    parser.add_argument("--skip-phoenix", action="store_true")
    args = parser.parse_args()

    if args.day_index < 1 or args.day_index > 14:
        print("FAIL: day-index must be 1..14", file=sys.stderr)
        return 1
    datetime.strptime(args.date, "%Y-%m-%d")

    project_root = Path(__file__).resolve().parent
    agent_root = project_root.parents[1]
    load_dotenv(agent_root / ".env", override=True)
    (project_root / "logs").mkdir(exist_ok=True)
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")

    tracer_provider = None
    if not args.skip_phoenix:
        from openinference.instrumentation.crewai import CrewAIInstrumentor
        from phoenix.otel import register

        tracer_provider = register(
            endpoint=args.phoenix_endpoint,
            project_name="vacation_planner",
            protocol="http/protobuf",
            auto_instrument=False,
            verbose=True,
        )
        CrewAIInstrumentor().instrument(skip_dep_check=True, tracer_provider=tracer_provider)

    from crewai.project import load_crew

    crew, default_inputs = load_crew(project_root / "crew.jsonc")
    for agent in crew.agents:
        llm = getattr(agent, "llm", None)
        if llm is not None and hasattr(llm, "stream"):
            llm.stream = False

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

    print(
        f"SMOKE day_plan: day {args.day_index} in {args.overnight_city} ({args.date})…",
        flush=True,
    )
    result = crew.kickoff(inputs=inputs)

    try:
        plan = _extract_day_plan(result)
        _assert_day_plan(
            plan,
            day_index=args.day_index,
            date_str=args.date,
            overnight_city=args.overnight_city,
        )
    except Exception as exc:
        print(f"FAIL: DayPlan validation failed: {exc}", file=sys.stderr)
        print(f"Raw result: {result!r}", file=sys.stderr)
        return 1

    print(plan.model_dump_json(indent=2))
    print(f"PASS: DayPlan with {len(plan.places)} places", flush=True)

    if tracer_provider is not None and hasattr(tracer_provider, "force_flush"):
        tracer_provider.force_flush(timeout_millis=10_000)
        print("Phoenix: http://localhost:6006 → project vacation_planner → Traces")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
