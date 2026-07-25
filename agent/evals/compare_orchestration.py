"""Compare day_plan (3-agent) vs day_plan_single on the same fixtures."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from evals.case import EvalCase, load_cases
from evals.harness import EvalResult, aggregate_metrics, run_case
from evals.preference_scorer import PreferenceScorer

Producer = Callable[[EvalCase], dict[str, Any]]

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


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


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


def run_orchestration_compare(
    *,
    cases: list[EvalCase] | None = None,
    producer: Producer,
    preference_scorer: PreferenceScorer | None = None,
    runs_dir: Path | None = None,
) -> dict[str, Any]:
    """Run each day_plan fixture under both crews; save raw outputs when runs_dir set."""
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
    arms: dict[str, ArmResult] = {}

    for crew in ("day_plan", "day_plan_single"):
        results: list[EvalResult] = []
        for case in unique:
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
                # Prefer envelope latency when present.
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

            if out_root is not None:
                arm_dir = out_root / crew
                arm_dir.mkdir(parents=True, exist_ok=True)
                (arm_dir / f"{case.id}.json").write_text(
                    json.dumps(output, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
            results.append(result)

        arms[crew] = ArmResult(
            crew=crew,
            results=results,
            aggregates=aggregate_metrics(results),
        )

    multi = arms["day_plan"].aggregates
    single = arms["day_plan_single"].aggregates
    keep, reasons = decide_keep_three_agent(multi, single)

    report = {
        "run_id": run_id,
        "case_count": len(unique),
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
    return report
