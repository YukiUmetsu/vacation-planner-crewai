"""Offline crew evaluation harness (fixture loading + result reporting).

LEARNING (you write later):
  - Golden fixtures under ``fixtures/``
  - Scoring rules in ``scorers.py``

This package only provides the plumbing so CI can discover tests without AWS.
"""

from __future__ import annotations

from evals.case import EvalCase, load_cases
from evals.harness import EvalResult, run_case, run_cases

__all__ = [
    "EvalCase",
    "EvalResult",
    "load_cases",
    "run_case",
    "run_cases",
]
