"""CLI for offline / live eval runs: ``uv run python -m evals``.

Examples:
  uv run python -m evals                 # score fixtures with sibling *.output.json
  uv run python -m evals --live          # call crew_kickoff.run_crew (needs AWS/model creds)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from evals.case import EvalCase, load_cases
from evals.harness import run_cases


def _offline_producer(case: EvalCase) -> dict[str, Any]:
    """Load ``fixtures/<id>.output.json`` (required for offline scoring)."""
    sibling = case.source_path.with_suffix(".output.json")
    if not sibling.is_file():
        raise FileNotFoundError(
            f"missing offline output {sibling.name}; add a golden or run with --live"
        )
    data = json.loads(sibling.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{sibling}: output must be a JSON object")
    return data


def _live_producer(case: EvalCase) -> dict[str, Any]:
    # Import lazily so offline runs do not need CrewAI on PATH quirks.
    agent_root = Path(__file__).resolve().parents[1]
    if str(agent_root) not in sys.path:
        sys.path.insert(0, str(agent_root))
    from crew_kickoff import run_crew

    return run_crew(case.crew, case.inputs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run vacation-planner crew evals")
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=None,
        help="Override fixtures directory (default: evals/fixtures)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Invoke real crews via crew_kickoff (needs credentials)",
    )
    args = parser.parse_args(argv)

    cases = load_cases(args.fixtures_dir)
    if not cases:
        print("No fixtures found.", file=sys.stderr)
        return 2

    if not args.live:
        runnable: list[EvalCase] = []
        for case in cases:
            sibling = case.source_path.with_suffix(".output.json")
            if sibling.is_file():
                runnable.append(case)
            else:
                print(f"SKIP  {case.id} (no {sibling.name})")
        cases = runnable
        if not cases:
            print("No offline outputs found (add fixtures/<id>.output.json or use --live).")
            return 0

    producer = _live_producer if args.live else _offline_producer
    results = run_cases(cases, producer)

    failed = 0
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status}  {result.case_id}")
        for msg in result.failures:
            print(f"       - {msg}")
        if not result.passed:
            failed += 1

    print(f"\n{len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
