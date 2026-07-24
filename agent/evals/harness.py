"""Run eval cases against a provided output (offline) or a callable producer."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from evals.case import EvalCase
from evals.preference_scorer import PreferenceScorer
from evals.scorers import collect_day_plan_metrics, score_output

Producer = Callable[[EvalCase], dict[str, Any]]


def unwrap_eval_output(output: dict[str, Any]) -> dict[str, Any]:
    """Prefer CrewEnvelope.result when present."""
    result = output.get("result")
    if isinstance(result, dict) and (
        "invocation" in output or "quality" in output or "day_index" in result
    ):
        return result
    return output


@dataclass(frozen=True)
class EvalResult:
    case_id: str
    passed: bool
    failures: tuple[str, ...]
    output: dict[str, Any] | None = None
    metrics: dict[str, float | int | bool] = field(default_factory=dict)


def run_case(
    case: EvalCase,
    output: dict[str, Any],
    *,
    preference_scorer: PreferenceScorer | None = None,
    latency_ms: float | None = None,
) -> EvalResult:
    domain = unwrap_eval_output(output)
    failures = tuple(score_output(domain, case))
    metrics: dict[str, float | int | bool] = {
        "schema_valid": 1.0 if len(failures) == 0 else 0.0,
        "hard_constraint_pass": 1.0 if len(failures) == 0 else 0.0,
    }
    if case.crew == "day_plan":
        metrics.update(
            collect_day_plan_metrics(
                domain, case, preference_scorer=preference_scorer
            )
        )
    if latency_ms is not None:
        metrics["latency_ms"] = float(latency_ms)
    # Cost stub until Bedrock usage is plumbed.
    metrics.setdefault("cost", 0.0)
    return EvalResult(
        case_id=case.id,
        passed=len(failures) == 0,
        failures=failures,
        output=output,
        metrics=metrics,
    )


def aggregate_metrics(results: Sequence[EvalResult]) -> dict[str, float]:
    """Mean of numeric metrics across cases (rates are 0–1)."""
    if not results:
        return {}
    keys = sorted({k for r in results for k in r.metrics})
    out: dict[str, float] = {}
    for key in keys:
        values = [float(r.metrics[key]) for r in results if key in r.metrics]
        if values:
            out[key] = sum(values) / len(values)
    # Alias common catalog names.
    if "schema_valid" in out:
        out["schema_valid_rate"] = out["schema_valid"]
    if "hard_constraint_pass" in out:
        out["hard_constraint_pass_rate"] = out["hard_constraint_pass"]
    return out


def run_cases(
    cases: Sequence[EvalCase],
    producer: Producer,
    *,
    preference_scorer: PreferenceScorer | None = None,
) -> list[EvalResult]:
    results: list[EvalResult] = []
    for case in cases:
        started = time.perf_counter()
        try:
            output = producer(case)
        except Exception as exc:  # noqa: BLE001 — eval boundary
            latency_ms = (time.perf_counter() - started) * 1000.0
            results.append(
                EvalResult(
                    case_id=case.id,
                    passed=False,
                    failures=(f"{type(exc).__name__}: {exc}",),
                    output=None,
                    metrics={
                        "schema_valid": 0.0,
                        "hard_constraint_pass": 0.0,
                        "cost": 0.0,
                        "latency_ms": latency_ms,
                    },
                )
            )
            continue
        latency_ms = (time.perf_counter() - started) * 1000.0
        if not isinstance(output, dict):
            results.append(
                EvalResult(
                    case_id=case.id,
                    passed=False,
                    failures=(
                        f"producer returned non-object: {type(output).__name__}",
                    ),
                    output=None,
                    metrics={
                        "schema_valid": 0.0,
                        "hard_constraint_pass": 0.0,
                        "cost": 0.0,
                        "latency_ms": latency_ms,
                    },
                )
            )
            continue
        results.append(
            run_case(
                case,
                output,
                preference_scorer=preference_scorer,
                latency_ms=latency_ms,
            )
        )
    return results
