"""Format offline graded metric aggregates as a text/JSON dashboard."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from evals.harness import EvalResult, aggregate_metrics


def build_metrics_report(
    results: Sequence[EvalResult],
    *,
    preference_judge: str = "heuristic",
    title: str = "Vacation planner offline eval metrics",
) -> dict[str, Any]:
    aggregates = aggregate_metrics(results)
    cases = [
        {
            "case_id": r.case_id,
            "passed": r.passed,
            "failures": list(r.failures),
            "metrics": dict(r.metrics),
        }
        for r in results
    ]
    return {
        "title": title,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "preference_judge": preference_judge,
        "summary": {
            "cases": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
        },
        "aggregates": aggregates,
        "cases": cases,
    }


def format_metrics_table(aggregates: dict[str, float]) -> str:
    if not aggregates:
        return "(no metrics)"
    width = max(len(k) for k in aggregates)
    lines = [f"{'metric'.ljust(width)}  value", "-" * (width + 10)]
    for key in sorted(aggregates):
        lines.append(f"{key.ljust(width)}  {aggregates[key]:.4f}")
    return "\n".join(lines)


def format_metrics_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    aggregates = report.get("aggregates") or {}
    lines = [
        f"# {report.get('title') or 'Eval metrics'}",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Preference judge: `{report.get('preference_judge')}`",
        f"- Cases: **{summary.get('passed', 0)}/{summary.get('cases', 0)}** passed",
        "",
        "## Aggregate rates",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key in sorted(aggregates):
        lines.append(f"| `{key}` | {float(aggregates[key]):.4f} |")
    lines.extend(["", "## Per case", ""])
    for case in report.get("cases") or []:
        status = "PASS" if case.get("passed") else "FAIL"
        lines.append(f"### {case.get('case_id')} — {status}")
        metrics = case.get("metrics") or {}
        if metrics:
            lines.append("")
            lines.append("| Metric | Value |")
            lines.append("| --- | ---: |")
            for key in sorted(metrics):
                val = metrics[key]
                if isinstance(val, bool):
                    lines.append(f"| `{key}` | {val} |")
                else:
                    lines.append(f"| `{key}` | {float(val):.4f} |")
        failures = case.get("failures") or []
        if failures:
            lines.append("")
            for msg in failures:
                lines.append(f"- {msg}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_metrics_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".md":
        path.write_text(format_metrics_markdown(report), encoding="utf-8")
    else:
        path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
