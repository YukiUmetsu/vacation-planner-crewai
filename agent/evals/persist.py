"""Persist offline eval runs to the dedicated metrics DynamoDB table."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from evals.case import EvalCase
from evals.harness import EvalResult, aggregate_metrics


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def experiment_key_for(dimensions: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(dimensions).encode("utf-8")).hexdigest()
    return digest[:16]


def fixture_suite_hash(cases: Sequence[EvalCase]) -> str:
    parts: list[str] = []
    for case in sorted(cases, key=lambda c: c.id):
        raw = case.source_path.read_bytes() if case.source_path.is_file() else b""
        parts.append(f"{case.id}:{hashlib.sha256(raw).hexdigest()}")
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def _git_sha() -> str:
    env = os.getenv("BACKEND_GIT_SHA", "").strip() or os.getenv("GIT_SHA", "").strip()
    if env:
        return env
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _utc_now_iso() -> str:
    """UTC timestamp suitable for DynamoDB keys and URL query params (Z suffix)."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _judge_model_id(preference_judge: str) -> str:
    """Keep in sync with ``LlmPreferenceScorer`` default resolution."""
    if preference_judge != "llm":
        return ""
    raw = (
        os.getenv("EVAL_JUDGE_MODEL_ID", "").strip()
        or os.getenv("CREW_MODEL_ID", "us.amazon.nova-lite-v1:0")
    )
    return raw.removeprefix("bedrock/")


def _prompt_fingerprint(crew_names: set[str]) -> tuple[str, str]:
    """Return (prompt_version, prompt_hash) for crews in the suite."""
    try:
        agent_root = Path(__file__).resolve().parents[1]
        models_root = str(agent_root / "models")
        if models_root not in sys.path:
            sys.path.insert(0, models_root)
        from vacation_planner_models.prompt_meta import (  # noqa: WPS433
            PROMPT_VERSIONS,
            prompt_hash_for_crew,
        )
    except Exception:  # noqa: BLE001
        return "", ""

    versions: list[str] = []
    hashes: list[str] = []
    crews_root = agent_root / "crews"
    for name in sorted(crew_names):
        versions.append(f"{name}:{PROMPT_VERSIONS.get(name, '')}")
        hashes.append(f"{name}:{prompt_hash_for_crew(crews_root / name)}")
    version = hashlib.sha256("|".join(versions).encode()).hexdigest()[:12]
    prompt_hash = hashlib.sha256("|".join(hashes).encode()).hexdigest()[:12]
    return version, prompt_hash


def build_experiment_dimensions(
    cases: Sequence[EvalCase],
    *,
    preference_judge: str,
    live: bool,
) -> dict[str, Any]:
    crews = {c.crew for c in cases}
    prompt_version, prompt_hash = _prompt_fingerprint(crews)
    return {
        "fixture_suite_hash": fixture_suite_hash(cases),
        "prompt_version": prompt_version,
        "prompt_hash": prompt_hash,
        "preference_judge": preference_judge,
        "judge_model_id": _judge_model_id(preference_judge),
        "model_id": os.getenv("CREW_MODEL_ID", "bedrock/us.amazon.nova-pro-v1:0"),
        "git_sha": _git_sha(),
        "live": bool(live),
    }


def _ensure_backend_on_path() -> None:
    backend_src = Path(__file__).resolve().parents[2] / "backend" / "src"
    if str(backend_src) not in sys.path:
        sys.path.insert(0, str(backend_src))


def persist_eval_results(
    results: Sequence[EvalResult],
    cases: Sequence[EvalCase],
    *,
    preference_judge: str,
    live: bool,
) -> dict[str, Any]:
    """Write run + case rows to DYNAMODB_METRICS_TABLE_NAME. Raises on failure."""
    _ensure_backend_on_path()
    from db.client import reset_clients  # noqa: WPS433
    from db import repository as repo  # noqa: WPS433

    reset_clients()
    dimensions = build_experiment_dimensions(
        cases, preference_judge=preference_judge, live=live
    )
    key = experiment_key_for(dimensions)
    started_at = _utc_now_iso()
    run_id = uuid.uuid4().hex[:12]
    aggregates = aggregate_metrics(results)
    passed_count = sum(1 for r in results if r.passed)

    repo.put_eval_run(
        run_id=run_id,
        started_at=started_at,
        experiment_key=key,
        dimensions=dimensions,
        aggregates=aggregates,
        case_count=len(results),
        passed_count=passed_count,
        updated_at=started_at,
    )
    for result in results:
        repo.put_eval_case(
            run_id=run_id,
            started_at=started_at,
            experiment_key=key,
            case_id=result.case_id,
            passed=result.passed,
            failures=list(result.failures),
            metrics=dict(result.metrics),
        )
    return {
        "run_id": run_id,
        "started_at": started_at,
        "experiment_key": key,
        "dimensions": dimensions,
        "aggregates": aggregates,
    }
