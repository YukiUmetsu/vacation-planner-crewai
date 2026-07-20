"""Smoke-test city_route: kickoff crew and assert a valid CityRoute.

Requires agent/.env (SERPER_API_KEY + AWS creds) and preferably Phoenix on :6006.

Usage:
  uv run python smoke_test.py
  uv run python smoke_test.py --destination Japan --day-count 7
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _inclusive_days(start: date, end: date) -> int:
    return (end - start).days + 1


def _extract_city_route(result):  # noqa: ANN001
    from models import CityRoute

    pydantic_out = getattr(result, "pydantic", None)
    if pydantic_out is not None:
        if isinstance(pydantic_out, CityRoute):
            return pydantic_out
        return CityRoute.model_validate(pydantic_out)

    raw = getattr(result, "raw", None) or str(result)
    if isinstance(raw, dict):
        return CityRoute.model_validate(raw)
    try:
        return CityRoute.model_validate_json(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return CityRoute.model_validate_json(raw[start : end + 1])
        raise


def _assert_route_fits_window(route, day_count: int) -> None:
    assert route.status == "proposed", f"expected status=proposed, got {route.status!r}"
    assert route.cities, "cities must be non-empty"
    assert route.total_nights == sum(c.nights for c in route.cities)
    for stop in route.cities:
        assert 1 <= stop.arrival_day_index <= day_count
        assert 1 <= stop.departure_day_index <= day_count
        assert stop.departure_day_index >= stop.arrival_day_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test city_route → CityRoute")
    parser.add_argument("--origin", default="San Francisco")
    parser.add_argument("--destination", default="Japan")
    parser.add_argument(
        "--destination-type",
        default="country",
        choices=["city", "country", "region"],
    )
    parser.add_argument("--start-date", default="2026-09-01")
    parser.add_argument("--end-date", default="2026-09-10")
    parser.add_argument("--day-count", type=int, default=None)
    parser.add_argument(
        "--preferences",
        default="culture, food, moderate pace",
    )
    parser.add_argument(
        "--phoenix-endpoint",
        default=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces"),
    )
    parser.add_argument(
        "--skip-phoenix",
        action="store_true",
        help="Run crew without OpenInference/Phoenix instrumentation",
    )
    args = parser.parse_args()

    start = _parse_date(args.start_date)
    end = _parse_date(args.end_date)
    if end < start:
        print("FAIL: end-date before start-date", file=sys.stderr)
        return 1
    day_count = args.day_count if args.day_count is not None else _inclusive_days(start, end)
    if day_count < 1 or day_count > 14:
        print("FAIL: day_count must be 1..14", file=sys.stderr)
        return 1
    if day_count != _inclusive_days(start, end):
        end = start + timedelta(days=day_count - 1)

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
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "day_count": str(day_count),
        "preferences": args.preferences,
    }

    print(f"SMOKE city_route: {args.destination} ({day_count} days)…", flush=True)
    result = crew.kickoff(inputs=inputs)

    try:
        route = _extract_city_route(result)
        _assert_route_fits_window(route, day_count)
    except Exception as exc:
        print(f"FAIL: CityRoute validation failed: {exc}", file=sys.stderr)
        print(f"Raw result: {result!r}", file=sys.stderr)
        return 1

    print(route.model_dump_json(indent=2))
    print(
        f"PASS: CityRoute with {len(route.cities)} cities, "
        f"total_nights={route.total_nights}",
        flush=True,
    )

    if tracer_provider is not None and hasattr(tracer_provider, "force_flush"):
        tracer_provider.force_flush(timeout_millis=10_000)
        print("Phoenix: http://localhost:6006 → project vacation_planner → Traces")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
