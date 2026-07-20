#!/usr/bin/env python3
"""End-to-end trip flow against DynamoDB Local (or moto-like fake crews).

Usage:
  docker compose up -d
  uv run python scripts/create_local_table.py
  export DYNAMODB_ENDPOINT=http://localhost:8000
  export DYNAMODB_TABLE_NAME=vacation-planner-local-table
  export AUTH_MODE=dev CREW_MODE=fake SAFETY_MODE=off
  uv run python scripts/smoke_trip_flow.py

  # Real crews (optional; needs CrewAI + agent/.env + Bedrock + Serper — not the Lambda path):
  # CREW_MODE=local uv run python scripts/smoke_trip_flow.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _event(method: str, path: str, body: dict | None = None) -> dict:
    event: dict = {
        "requestContext": {"http": {"method": method}},
        "rawPath": path,
        "headers": {"x-dev-user-sub": os.getenv("DEV_USER_SUB", "smoke-user")},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke trip API flow")
    parser.add_argument("--origin", default="Chicago")
    parser.add_argument("--destination", default="Japan")
    parser.add_argument(
        "--destination-type",
        default="country",
        choices=["city", "country", "region"],
    )
    parser.add_argument("--start-date", default="2026-09-01")
    parser.add_argument("--end-date", default="2026-09-07")
    parser.add_argument("--skip-crew", action="store_true", help="Force CREW_MODE=fake")
    args = parser.parse_args()

    os.environ.setdefault("DYNAMODB_ENDPOINT", "http://localhost:8000")
    os.environ.setdefault("DYNAMODB_TABLE_NAME", "vacation-planner-local-table")
    os.environ.setdefault("AUTH_MODE", "dev")
    os.environ.setdefault("SAFETY_MODE", "keyword")
    if args.skip_crew:
        os.environ["CREW_MODE"] = "fake"
    else:
        os.environ.setdefault("CREW_MODE", "fake")

    from db.client import reset_clients
    from handler import handler

    reset_clients()

    print(f"SMOKE: create {args.destination} ({args.destination_type})…", flush=True)
    create = handler(
        _event(
            "POST",
            "/trips",
            {
                "origin": args.origin,
                "destination": args.destination,
                "destination_type": args.destination_type,
                "start_date": args.start_date,
                "end_date": args.end_date,
                "preferences": "culture, food, moderate pace",
            },
        )
    )
    if create["statusCode"] not in {200, 201}:
        print(f"FAIL create: {create}", file=sys.stderr)
        return 1
    created = json.loads(create["body"])
    trip_id = created["trip"]["trip_id"]
    print(f"  trip_id={trip_id} status={created['trip']['status']}", flush=True)

    if args.destination_type != "city":
        print("SMOKE: propose-cities…", flush=True)
        proposed = handler(_event("POST", f"/trips/{trip_id}/propose-cities"))
        if proposed["statusCode"] != 200:
            print(f"FAIL propose: {proposed}", file=sys.stderr)
            return 1
        route = json.loads(proposed["body"])["route"]
        print(f"  cities={[c['city'] for c in route['cities']]}", flush=True)

        print("SMOKE: confirm cities…", flush=True)
        confirmed = handler(
            _event(
                "PUT",
                f"/trips/{trip_id}/cities",
                {
                    "destination_type": route["destination_type"],
                    "cities": route["cities"],
                    "rationale": route.get("rationale") or "",
                    "total_nights": route.get("total_nights") or 0,
                    "status": "confirmed",
                },
            )
        )
        if confirmed["statusCode"] != 200:
            print(f"FAIL confirm: {confirmed}", file=sys.stderr)
            return 1

    print("SMOKE: plan-next-day…", flush=True)
    planned = handler(_event("POST", f"/trips/{trip_id}/plan-next-day"))
    if planned["statusCode"] != 200:
        print(f"FAIL plan: {planned}", file=sys.stderr)
        return 1
    day = json.loads(planned["body"])["day"]
    print(f"  day_index={day['day_index']} places={len(day.get('places') or [])}", flush=True)

    print("SMOKE: get trip…", flush=True)
    got = handler(_event("GET", f"/trips/{trip_id}"))
    if got["statusCode"] != 200:
        print(f"FAIL get: {got}", file=sys.stderr)
        return 1
    bundle = json.loads(got["body"])
    types = {"TRIP"}
    if bundle.get("route"):
        types.add("ROUTE")
    if bundle.get("days"):
        types.add("DAY")
    print(f"  entities={sorted(types)}", flush=True)

    if "DAY" not in types:
        print("FAIL: expected DAY in bundle", file=sys.stderr)
        return 1

    print("PASS: trip flow complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
