"""Compare day_plan (3-agent) vs day_plan_single on the same fixtures."""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from evals.case import EvalCase, load_cases
from evals.harness import EvalResult, aggregate_metrics, run_case
from evals.preference_scorer import PreferenceScorer

Producer = Callable[[EvalCase], dict[str, Any]]

# Curated subset for faster live orchestration compares (~8 × 2 arms).
# Covers prefs, food-balance, visited, closed-day, China/Amap, and a dense city.
ORCHESTRATION_SMOKE_IDS: tuple[str, ...] = (
    "day_plan_preference_food",
    "day_plan_preference_mismatch",
    "day_plan_balance_food_only",
    "day_plan_avoid_visited",
    "day_plan_weekday_closed",
    "day_plan_shanghai_amap",
    "day_plan_kyoto_dense",
    "day_plan_seoul",
)

ARM_NAMES: tuple[str, ...] = ("day_plan", "day_plan_single")

# Pre-declared decision rule (see docs/PLANNING_QUALITY.md).
HARD_PASS_DELTA_PP = 10.0
FAILURE_BUNDLE_RELATIVE_DROP = 0.25
PREF_SCORE_DELTA = 0.10
MAX_LATENCY_RATIO = 2.5
MAX_COST_RATIO = 3.0


@dataclass(frozen=True)
class ArmResult:
    crew: str
    results: list[EvalResult]
    aggregates: dict[str, float]


@dataclass(frozen=True)
class _ArmCaseOutcome:
    crew: str
    result: EvalResult
    output: dict[str, Any]
    latency_ms: float


def _failure_bundle_rate(agg: dict[str, float]) -> float:
    """Case-level failure rates only (do not mix place-fraction closed rate)."""
    closed = agg.get("closed_place_case_rate")
    if closed is None:
        # Fallback: treat any positive mean closed fraction as a soft signal.
        closed = 1.0 if float(agg.get("closed_place_rate", 0.0)) > 0 else 0.0
    return float(
        agg.get("food_only_day_rate", 0.0)
        + agg.get("duplicate_rate", 0.0)
        + float(closed)
    )


def decide_keep_three_agent(
    multi: dict[str, float],
    single: dict[str, float],
) -> tuple[bool, list[str]]:
    """Return (keep_three_agent, reasons)."""
    reasons: list[str] = []
    multi_hard = float(multi.get("hard_constraint_pass_rate", multi.get("hard_constraint_pass", 0.0)))
    single_hard = float(
        single.get("hard_constraint_pass_rate", single.get("hard_constraint_pass", 0.0))
    )
    hard_delta_pp = (multi_hard - single_hard) * 100.0
    if hard_delta_pp >= HARD_PASS_DELTA_PP:
        reasons.append(
            f"hard_constraint_pass_rate +{hard_delta_pp:.1f} pp (≥ {HARD_PASS_DELTA_PP})"
        )

    multi_bundle = _failure_bundle_rate(multi)
    single_bundle = _failure_bundle_rate(single)
    if single_bundle > 0:
        relative_drop = (single_bundle - multi_bundle) / single_bundle
        if relative_drop >= FAILURE_BUNDLE_RELATIVE_DROP:
            reasons.append(
                f"food_only+duplicate+closed relative drop {relative_drop:.0%} "
                f"(≥ {FAILURE_BUNDLE_RELATIVE_DROP:.0%})"
            )

    multi_pref = float(multi.get("preference_relevance_score", 0.0))
    single_pref = float(single.get("preference_relevance_score", 0.0))
    pref_delta = multi_pref - single_pref
    if pref_delta >= PREF_SCORE_DELTA:
        reasons.append(
            f"preference_relevance_score +{pref_delta:.2f} (≥ {PREF_SCORE_DELTA})"
        )

    quality_win = bool(reasons)

    multi_lat = multi.get("latency_ms")
    single_lat = single.get("latency_ms")
    latency_ok = True
    if multi_lat is not None and single_lat and float(single_lat) > 0:
        ratio = float(multi_lat) / float(single_lat)
        latency_ok = ratio <= MAX_LATENCY_RATIO
        if not latency_ok:
            reasons.append(
                f"latency ratio {ratio:.2f}x exceeds budget {MAX_LATENCY_RATIO}x"
            )

    multi_cost = multi.get("cost_usd", multi.get("cost"))
    single_cost = single.get("cost_usd", single.get("cost"))
    cost_ok = True
    if multi_cost is None or single_cost is None:
        cost_ok = False
        reasons.append("cost unavailable on one or both arms — cannot justify three-agent")
    elif float(single_cost) <= 0:
        cost_ok = False
        reasons.append("single-call cost is zero/missing — cannot apply cost budget")
    else:
        ratio = float(multi_cost) / float(single_cost)
        cost_ok = ratio <= MAX_COST_RATIO
        if not cost_ok:
            reasons.append(
                f"cost ratio {ratio:.2f}x exceeds budget {MAX_COST_RATIO}x"
            )

    keep = quality_win and latency_ok and cost_ok
    if not quality_win:
        reasons.append("quality deltas below decision bar → prefer single-call for MVP")
    return keep, reasons


def _progress(msg: str) -> None:
    """Always write progress to stderr so stdout redirects cannot swallow it."""
    print(msg, file=sys.stderr, flush=True)


def format_orchestration_summary(report: dict[str, Any]) -> str:
    """Human-readable decision + side-by-side comparison table."""
    multi = report["arms"]["day_plan"]
    single = report["arms"]["day_plan_single"]
    m_agg = multi["aggregates"]
    s_agg = single["aggregates"]
    decision = report["decision"]
    keep = decision["keep_three_agent"]
    cases = int(report.get("case_count") or 0)

    def _pct(arm_agg: dict[str, float], key: str) -> str:
        return f"{100.0 * float(arm_agg.get(key, 0.0)):.0f}%"

    def _num(arm_agg: dict[str, float], key: str, *, decimals: int = 2) -> str:
        val = arm_agg.get(key)
        if val is None:
            return "—"
        return f"{float(val):.{decimals}f}"

    m_lat = float(m_agg.get("latency_ms") or 0.0) / 1000.0
    s_lat = float(s_agg.get("latency_ms") or 0.0) / 1000.0
    lat_ratio = (m_lat / s_lat) if s_lat > 0 else float("nan")
    m_cost = m_agg.get("cost_usd", m_agg.get("cost"))
    s_cost = s_agg.get("cost_usd", s_agg.get("cost"))
    if m_cost is not None and s_cost is not None and float(s_cost) > 0:
        cost_ratio = float(m_cost) / float(s_cost)
        cost_ratio_s = f"{cost_ratio:.2f}×"
    else:
        cost_ratio_s = "—"

    hard_delta = (
        float(m_agg.get("hard_constraint_pass_rate", 0.0))
        - float(s_agg.get("hard_constraint_pass_rate", 0.0))
    ) * 100.0

    m_cost_s = f"${float(m_cost):.3f}" if m_cost is not None else "—"
    s_cost_s = f"${float(s_cost):.3f}" if s_cost is not None else "—"
    lat_ratio_s = f"{lat_ratio:.2f}×" if s_lat > 0 else "—"

    lines = [
        f"**Decision:** keep 3-agent = **{keep}**",
        "",
        "| Check | Multi (`day_plan`) | Single (`day_plan_single`) | Result |",
        "| --- | --- | --- | --- |",
        (
            f"| Pass / fail | **{multi['passed']}/{cases}** pass "
            f"({multi['failed']} fail) | **{single['passed']}/{cases}** pass "
            f"({single['failed']} fail) | — |"
        ),
        (
            f"| Hard-constraint pass | **{_pct(m_agg, 'hard_constraint_pass_rate')}** | "
            f"**{_pct(s_agg, 'hard_constraint_pass_rate')}** | "
            f"**{hard_delta:+.0f} pp** |"
        ),
        (
            f"| Schema valid | {_pct(m_agg, 'schema_valid_rate')} | "
            f"{_pct(s_agg, 'schema_valid_rate')} | — |"
        ),
        (
            f"| Preference relevance | {_num(m_agg, 'preference_relevance_score')} | "
            f"{_num(s_agg, 'preference_relevance_score')} | — |"
        ),
        (
            f"| Mean latency | {m_lat:.0f}s | {s_lat:.0f}s | {lat_ratio_s} |"
        ),
        (
            f"| Cost / case | {m_cost_s} | {s_cost_s} | {cost_ratio_s} |"
        ),
        "",
        "### Decision reasons",
        "",
        *[f"- {r}" for r in decision.get("reasons") or []],
    ]
    return "\n".join(lines)


def format_orchestration_progress_markdown(
    *,
    run_id: str,
    case_count: int,
    parallel_arms: bool,
    progress: list[str],
    completed_cases: int,
) -> str:
    """In-progress report (rewritten after each case so the .md keeps pace)."""
    lines = [
        "# Orchestration compare (in progress)",
        "",
        f"run_id: `{run_id}`",
        f"cases: {completed_cases}/{case_count} complete",
        f"parallel_arms: `{parallel_arms}`",
        "",
        "_Summary table appears when the run finishes._",
        "",
        "## Progress",
        "",
    ]
    if progress:
        lines.extend(f"- {line}" for line in progress)
    else:
        lines.append("_Waiting for first case…_")
    return "\n".join(lines).rstrip() + "\n"


def format_orchestration_markdown(report: dict[str, Any]) -> str:
    """Full markdown report: summary table, progress log, detailed aggregates."""
    from evals.report import format_metrics_table

    lines = [
        "# Orchestration compare",
        "",
        f"run_id: `{report['run_id']}`",
        f"cases: {report['case_count']}",
        f"parallel_arms: `{report.get('parallel_arms')}`",
        "",
        "## Summary",
        "",
        format_orchestration_summary(report),
        "",
        "## Progress",
        "",
    ]
    progress = report.get("progress") or []
    if progress:
        lines.extend(f"- {line}" for line in progress)
    else:
        lines.append("_No progress events recorded._")

    lines.extend(
        [
            "",
            "## Detailed aggregates",
            "",
            "### day_plan",
            "",
            (
                f"passed={report['arms']['day_plan']['passed']} "
                f"failed={report['arms']['day_plan']['failed']}"
            ),
            "",
            "```",
            format_metrics_table(report["arms"]["day_plan"]["aggregates"]),
            "```",
            "",
            "### day_plan_single",
            "",
            (
                f"passed={report['arms']['day_plan_single']['passed']} "
                f"failed={report['arms']['day_plan_single']['failed']}"
            ),
            "",
            "```",
            format_metrics_table(report["arms"]["day_plan_single"]["aggregates"]),
            "```",
            "",
        ]
    )
    for arm_name in ARM_NAMES:
        sample = report["arms"][arm_name].get("sample_failures") or []
        if sample:
            lines.extend([f"### {arm_name} sample failures", ""])
            lines.extend(f"- {s}" for s in sample)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _run_arm_case(
    *,
    case: EvalCase,
    crew: str,
    producer: Producer,
    preference_scorer: PreferenceScorer | None,
) -> _ArmCaseOutcome:
    overridden = EvalCase(
        id=case.id,
        crew=crew,  # type: ignore[arg-type]
        inputs=case.inputs,
        expected=case.expected,
        source_path=case.source_path,
    )
    started = time.perf_counter()
    try:
        output = producer(overridden)
        latency_ms = (time.perf_counter() - started) * 1000.0
        inv = (
            output.get("invocation")
            if isinstance(output.get("invocation"), dict)
            else {}
        )
        if isinstance(inv.get("latency_ms"), (int, float)):
            latency_ms = float(inv["latency_ms"])
        result = run_case(
            overridden,
            output,
            preference_scorer=preference_scorer,
            latency_ms=latency_ms,
        )
    except Exception as exc:  # noqa: BLE001
        latency_ms = (time.perf_counter() - started) * 1000.0
        result = EvalResult(
            case_id=case.id,
            passed=False,
            failures=(f"producer error: {type(exc).__name__}: {exc}",),
            output=None,
            metrics={
                "schema_valid": 0.0,
                "hard_constraint_pass": 0.0,
                "latency_ms": latency_ms,
            },
        )
        output = {"error": str(exc)}
    return _ArmCaseOutcome(
        crew=crew, result=result, output=output, latency_ms=latency_ms
    )


def _persist_arm_output(
    *,
    out_root: Path | None,
    crew: str,
    case_id: str,
    output: dict[str, Any],
) -> None:
    if out_root is None:
        return
    arm_dir = out_root / crew
    arm_dir.mkdir(parents=True, exist_ok=True)
    (arm_dir / f"{case_id}.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def run_orchestration_compare(
    *,
    cases: list[EvalCase] | None = None,
    producer: Producer,
    preference_scorer: PreferenceScorer | None = None,
    runs_dir: Path | None = None,
    parallel_arms: bool = True,
    report_path: Path | None = None,
) -> dict[str, Any]:
    """Run each day_plan fixture under both crews; save raw outputs when runs_dir set.

    By default both arms run in parallel per case (wall ≈ multi-arm time).
    Pass ``parallel_arms=False`` for sequential arms (debugging / rate limits).

    When ``report_path`` is a ``.md`` file, it is rewritten after every case with
    the live progress log, then replaced by the full summary report at the end.
    """
    base_cases = [
        c
        for c in (cases if cases is not None else load_cases())
        if c.crew in {"day_plan", "day_plan_single"}
    ]
    # Deduplicate by id — compare always overrides crew.
    by_id: dict[str, EvalCase] = {}
    for case in base_cases:
        by_id[case.id] = case
    unique = list(by_id.values())

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_root = runs_dir / run_id if runs_dir is not None else None
    results_by_crew: dict[str, list[EvalResult]] = {name: [] for name in ARM_NAMES}
    progress_log: list[str] = []
    progress_file = out_root / "progress.log" if out_root is not None else None
    live_md = (
        report_path
        if report_path is not None and report_path.suffix.lower() == ".md"
        else None
    )

    def _emit(msg: str) -> None:
        _progress(msg)
        progress_log.append(msg)
        if progress_file is not None:
            progress_file.parent.mkdir(parents=True, exist_ok=True)
            with progress_file.open("a", encoding="utf-8") as fh:
                fh.write(msg + "\n")

    def _flush_live_report(*, completed_cases: int) -> None:
        if live_md is None:
            return
        live_md.parent.mkdir(parents=True, exist_ok=True)
        live_md.write_text(
            format_orchestration_progress_markdown(
                run_id=run_id,
                case_count=len(unique),
                parallel_arms=parallel_arms,
                progress=progress_log,
                completed_cases=completed_cases,
            ),
            encoding="utf-8",
        )

    mode = "parallel arms" if parallel_arms else "sequential arms"
    header = (
        f"Orchestration compare run_id={run_id} cases={len(unique)} "
        f"({mode}; {len(unique) * len(ARM_NAMES)} crew runs)"
    )
    _emit(header)
    _flush_live_report(completed_cases=0)

    for idx, case in enumerate(unique, start=1):
        start_line = f"[{idx}/{len(unique)}] {case.id} …"
        _emit(start_line)
        _flush_live_report(completed_cases=idx - 1)
        outcomes: list[_ArmCaseOutcome] = []
        if parallel_arms:
            with ThreadPoolExecutor(max_workers=len(ARM_NAMES)) as pool:
                futures = {
                    pool.submit(
                        _run_arm_case,
                        case=case,
                        crew=crew,
                        producer=producer,
                        preference_scorer=preference_scorer,
                    ): crew
                    for crew in ARM_NAMES
                }
                for fut in as_completed(futures):
                    outcomes.append(fut.result())
        else:
            for crew in ARM_NAMES:
                outcomes.append(
                    _run_arm_case(
                        case=case,
                        crew=crew,
                        producer=producer,
                        preference_scorer=preference_scorer,
                    )
                )

        # Stable print / append order: day_plan then day_plan_single.
        by_crew = {o.crew: o for o in outcomes}
        for crew in ARM_NAMES:
            outcome = by_crew[crew]
            _persist_arm_output(
                out_root=out_root,
                crew=crew,
                case_id=case.id,
                output=outcome.output,
            )
            results_by_crew[crew].append(outcome.result)
            status = "PASS" if outcome.result.passed else "FAIL"
            _emit(f"  {crew}: {status} ({outcome.latency_ms / 1000.0:.1f}s)")
        _flush_live_report(completed_cases=idx)

    arms: dict[str, ArmResult] = {}
    for crew in ARM_NAMES:
        crew_results = results_by_crew[crew]
        arms[crew] = ArmResult(
            crew=crew,
            results=crew_results,
            aggregates=aggregate_metrics(crew_results),
        )
        _emit(
            f"  → {crew}: passed={sum(1 for r in crew_results if r.passed)} "
            f"failed={sum(1 for r in crew_results if not r.passed)}"
        )

    multi = arms["day_plan"].aggregates
    single = arms["day_plan_single"].aggregates
    keep, reasons = decide_keep_three_agent(multi, single)

    def _sample_failures(arm: ArmResult, *, limit: int = 3) -> list[str]:
        out: list[str] = []
        for result in arm.results:
            if result.passed:
                continue
            detail = "; ".join(result.failures) if result.failures else "failed"
            out.append(f"{result.case_id}: {detail[:240]}")
            if len(out) >= limit:
                break
        return out

    report = {
        "run_id": run_id,
        "case_count": len(unique),
        "parallel_arms": parallel_arms,
        "progress": progress_log,
        "decision": {
            "keep_three_agent": keep,
            "reasons": reasons,
            "rule": {
                "hard_pass_delta_pp": HARD_PASS_DELTA_PP,
                "failure_bundle_relative_drop": FAILURE_BUNDLE_RELATIVE_DROP,
                "pref_score_delta": PREF_SCORE_DELTA,
                "max_latency_ratio": MAX_LATENCY_RATIO,
                "max_cost_ratio": MAX_COST_RATIO,
            },
        },
        "arms": {
            name: {
                "aggregates": arm.aggregates,
                "passed": sum(1 for r in arm.results if r.passed),
                "failed": sum(1 for r in arm.results if not r.passed),
                "sample_failures": _sample_failures(arm),
            }
            for name, arm in arms.items()
        },
        "deltas": {
            key: float(multi.get(key, 0.0)) - float(single.get(key, 0.0))
            for key in sorted(set(multi) | set(single))
        },
    }
    if out_root is not None:
        out_root.mkdir(parents=True, exist_ok=True)
        (out_root / "compare.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        report["runs_dir"] = str(out_root)
    if live_md is not None:
        live_md.parent.mkdir(parents=True, exist_ok=True)
        live_md.write_text(format_orchestration_markdown(report), encoding="utf-8")
        report["report_path"] = str(live_md)
    return report
