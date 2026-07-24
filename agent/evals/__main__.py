"""CLI for offline / live eval runs: ``uv run python -m evals``.

Examples:
  uv run python -m evals
  uv run python -m evals --live
  uv run python -m evals --preference-judge llm --report reports/metrics.md
  uv run python -m evals --persist   # write to DynamoDB (DYNAMODB_METRICS_TABLE_NAME)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from evals.case import EvalCase, load_cases
from evals.harness import aggregate_metrics, run_cases
from evals.preference_scorer import resolve_preference_scorer
from evals.report import (
    build_metrics_report,
    format_metrics_table,
    write_metrics_report,
)


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
    parser.add_argument(
        "--preference-judge",
        choices=("heuristic", "llm"),
        default="heuristic",
        help="Scorer backend for preference_relevance_score (default: heuristic)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write graded metrics dashboard to .json or .md",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Write run + case metrics to DynamoDB (DYNAMODB_METRICS_TABLE_NAME)",
    )
    parser.add_argument(
        "--persist-required",
        action="store_true",
        help="Exit non-zero if --persist fails (default: soft-fail with warning)",
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

    try:
        preference_scorer = resolve_preference_scorer(args.preference_judge)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    producer = _live_producer if args.live else _offline_producer
    results = run_cases(cases, producer, preference_scorer=preference_scorer)

    failed = 0
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status}  {result.case_id}")
        for msg in result.failures:
            print(f"       - {msg}")
        if not result.passed:
            failed += 1

    print(f"\n{len(results) - failed}/{len(results)} passed")

    aggregates = aggregate_metrics(results)
    print("\n=== Graded metrics (aggregate) ===")
    print(format_metrics_table(aggregates))

    report = build_metrics_report(
        results, preference_judge=args.preference_judge
    )
    if args.report is not None:
        write_metrics_report(report, args.report)
        print(f"\nWrote metrics report → {args.report}")

    if args.persist or args.persist_required:
        from evals.persist import persist_eval_results

        try:
            persisted = persist_eval_results(
                results,
                cases,
                preference_judge=args.preference_judge,
                live=bool(args.live),
            )
            print(
                "\nPersisted eval run "
                f"experiment_key={persisted['experiment_key']} "
                f"run_id={persisted['run_id']}"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"\nPersist failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            if args.persist_required:
                return 2

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
