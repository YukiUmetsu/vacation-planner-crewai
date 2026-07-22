"""Run eval cases against a provided output (offline) or a callable producer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from evals.case import EvalCase
from evals.scorers import score_output

Producer = Callable[[EvalCase], dict[str, Any]]


@dataclass(frozen=True)
class EvalResult:
    case_id: str
    passed: bool
    failures: tuple[str, ...]
    output: dict[str, Any] | None = None


def run_case(case: EvalCase, output: dict[str, Any]) -> EvalResult:
    failures = tuple(score_output(output, case))
    return EvalResult(
        case_id=case.id,
        passed=len(failures) == 0,
        failures=failures,
        output=output,
    )


def run_cases(
    cases: Sequence[EvalCase],
    producer: Producer,
) -> list[EvalResult]:
    results: list[EvalResult] = []
    for case in cases:
        try:
            output = producer(case)
        except Exception as exc:  # noqa: BLE001 — eval boundary
            results.append(
                EvalResult(
                    case_id=case.id,
                    passed=False,
                    failures=(f"{type(exc).__name__}: {exc}",),
                    output=None,
                )
            )
            continue
        if not isinstance(output, dict):
            results.append(
                EvalResult(
                    case_id=case.id,
                    passed=False,
                    failures=(f"producer returned non-object: {type(output).__name__}",),
                    output=None,
                )
            )
            continue
        results.append(run_case(case, output))
    return results
