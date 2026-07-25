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
    parser.add_argument(
        "--compare-orchestration",
        action="store_true",
        help="Run each day_plan fixture under day_plan and day_plan_single; write pairwise report",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=None,
        help="Directory for raw compare outputs (default: evals/runs when comparing)",
    )
    parser.add_argument(
        "--model-id",
        default=None,
        help="Optional CREW_MODEL_ID override for live / compare runs",
    )
    args = parser.parse_args(argv)

    if args.model_id:
        import os

        os.environ["CREW_MODEL_ID"] = args.model_id

    cases = load_cases(args.fixtures_dir)
    if not cases:
        print("No fixtures found.", file=sys.stderr)
        return 2

    try:
        preference_scorer = resolve_preference_scorer(args.preference_judge)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.compare_orchestration:
        from evals.compare_orchestration import run_orchestration_compare

        if not args.live:
            print(
                "ERROR: --compare-orchestration requires --live "
                "(or provide a custom producer in tests).",
                file=sys.stderr,
            )
            return 2
        runs_dir = args.runs_dir or (Path(__file__).resolve().parent / "runs")
        report = run_orchestration_compare(
            cases=cases,
            producer=_live_producer,
            preference_scorer=preference_scorer,
            runs_dir=runs_dir,
        )
        print(json.dumps(report["decision"], indent=2))
        print("\n=== day_plan aggregates ===")
        print(format_metrics_table(report["arms"]["day_plan"]["aggregates"]))
        print("\n=== day_plan_single aggregates ===")
        print(format_metrics_table(report["arms"]["day_plan_single"]["aggregates"]))
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            if args.report.suffix.lower() == ".json":
                args.report.write_text(
                    json.dumps(report, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            else:
                lines = [
                    "# Orchestration compare",
                    "",
                    f"run_id: `{report['run_id']}`",
                    f"cases: {report['case_count']}",
                    "",
                    "## Decision",
                    "",
                    f"- keep_three_agent: **{report['decision']['keep_three_agent']}**",
                    *[f"- {r}" for r in report["decision"]["reasons"]],
                    "",
                    "## Aggregates",
                    "",
                    "### day_plan",
                    "",
                    "```",
                    format_metrics_table(report["arms"]["day_plan"]["aggregates"]),
                    "```",
                    "",
                    "### day_plan_single",
                    "",
                    "```",
                    format_metrics_table(
                        report["arms"]["day_plan_single"]["aggregates"]
                    ),
                    "```",
                    "",
                ]
                args.report.write_text("\n".join(lines), encoding="utf-8")
            print(f"\nWrote compare report → {args.report}")
        if report.get("runs_dir"):
            print(f"Raw outputs → {report['runs_dir']}")
        return 0 if report["decision"]["keep_three_agent"] is not None else 0

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
