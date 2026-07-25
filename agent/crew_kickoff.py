"""Run CrewAI day_plan / city_route crews in-process (no AgentCore).

Used by local smoke / learning and AgentCore ``main.py``.

Crew adapters use unique modules (``day_models`` / ``city_models``) so both
crews can load in one process without ``models`` name clashes.

Returns a CrewEnvelope dict: ``{result, quality?, invocation}``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

CrewName = Literal["day_plan", "day_plan_single", "city_route", "suggest_place"]

_CREW_MODEL_ATTR: dict[CrewName, str] = {
    "day_plan": "DayPlanWithQuality",
    "day_plan_single": "DayPlanWithQuality",
    "city_route": "CityRoute",
    "suggest_place": "Place",
}

# BFF may attach this key; stripped before crew kickoff.
_SLIM_FLAG_KEY = "__context_was_slimmed"


def agent_root() -> Path:
    env = os.getenv("AGENT_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parent


def crews_root() -> Path:
    env = os.getenv("AGENT_CREWS_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return agent_root() / "crews"


@lru_cache(maxsize=1)
def _load_dotenv_once() -> None:
    env_path = agent_root() / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=True)
    except ImportError:
        if not env_path.is_file():
            pass
        else:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
    from runtime_secrets import ensure_amap_web_key, ensure_serper_api_key

    ensure_serper_api_key()
    ensure_amap_web_key()


def _ensure_import_paths(crew_dir: Path) -> None:
    """Crew dir (for day_models/city_models) + shared models package on sys.path."""
    models_root = str((agent_root() / "models").resolve())
    if models_root not in sys.path:
        sys.path.insert(0, models_root)
    crew_str = str(crew_dir.resolve())
    if crew_str in sys.path:
        sys.path.remove(crew_str)
    sys.path.insert(0, crew_str)


def _disable_llm_stream(crew: Any) -> None:
    for agent in crew.agents:
        llm = getattr(agent, "llm", None)
        if llm is not None and hasattr(llm, "stream"):
            llm.stream = False


def extract_pydantic_dict(result: Any, model_cls: type) -> dict[str, Any]:
    """Turn a CrewAI kickoff result into a JSON-serializable dict."""
    pydantic_out = getattr(result, "pydantic", None)
    if pydantic_out is not None:
        if isinstance(pydantic_out, model_cls):
            return pydantic_out.model_dump(mode="json")
        return model_cls.model_validate(pydantic_out).model_dump(mode="json")

    raw = getattr(result, "raw", None) or str(result)
    if isinstance(raw, dict):
        return model_cls.model_validate(raw).model_dump(mode="json")
    if isinstance(raw, model_cls):
        return raw.model_dump(mode="json")

    try:
        return model_cls.model_validate_json(raw).model_dump(mode="json")
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return model_cls.model_validate_json(raw[start : end + 1]).model_dump(
                mode="json"
            )
        raise


def _model_class(crew_name: CrewName) -> type:
    from vacation_planner_models import CityRoute, DayPlanWithQuality, Place

    if crew_name in {"day_plan", "day_plan_single"}:
        return DayPlanWithQuality
    if crew_name == "suggest_place":
        return Place
    return CityRoute


def _as_nonneg_int(value: Any) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _usage_dict_from_obj(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if hasattr(raw, "model_dump"):
        try:
            dumped = raw.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:  # noqa: BLE001
            pass
    if isinstance(raw, dict):
        return raw
    # UsageMetrics-like / LiteLLM usage objects
    return {
        "prompt_tokens": getattr(raw, "prompt_tokens", None),
        "completion_tokens": getattr(raw, "completion_tokens", None),
        "total_tokens": getattr(raw, "total_tokens", None),
        "input_tokens": getattr(raw, "input_tokens", None),
        "output_tokens": getattr(raw, "output_tokens", None),
        "prompt_token_count": getattr(raw, "prompt_token_count", None),
        "completion_token_count": getattr(raw, "completion_token_count", None),
        "total_token_count": getattr(raw, "total_token_count", None),
    }


def _usage_dict_has_tokens(raw: dict[str, Any]) -> bool:
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "input_tokens",
        "output_tokens",
        "prompt_token_count",
        "completion_token_count",
        "total_token_count",
    ):
        if _as_nonneg_int(raw.get(key)) is not None:
            return True
    nested = raw.get("usage")
    if isinstance(nested, dict):
        return _usage_dict_has_tokens(nested)
    return False


def extract_token_usage(result: Any) -> dict[str, int]:
    """Pull prompt/completion/total tokens from a CrewAI kickoff result."""
    candidates: list[Any] = [
        getattr(result, "token_usage", None),
        getattr(result, "usage_metrics", None),
        getattr(result, "usage", None),
    ]
    for attr in ("token_usage", "usage_metrics"):
        nested = getattr(result, attr, None)
        if nested is not None and not isinstance(nested, dict):
            sr = getattr(nested, "successful_requests", None)
            if sr is not None:
                candidates.append(sr)

    raw_dict: dict[str, Any] | None = None
    for cand in candidates:
        parsed = _usage_dict_from_obj(cand)
        if not parsed or not _usage_dict_has_tokens(parsed):
            continue
        raw_dict = parsed
        break
    if not raw_dict:
        return {}

    nested_usage = raw_dict.get("usage")
    if isinstance(nested_usage, dict):
        raw_dict = {**raw_dict, **nested_usage}

    prompt = _as_nonneg_int(
        raw_dict.get("prompt_tokens")
        if raw_dict.get("prompt_tokens") is not None
        else raw_dict.get("input_tokens")
        if raw_dict.get("input_tokens") is not None
        else raw_dict.get("prompt_token_count")
    )
    completion = _as_nonneg_int(
        raw_dict.get("completion_tokens")
        if raw_dict.get("completion_tokens") is not None
        else raw_dict.get("output_tokens")
        if raw_dict.get("output_tokens") is not None
        else raw_dict.get("completion_token_count")
    )
    total = _as_nonneg_int(
        raw_dict.get("total_tokens")
        if raw_dict.get("total_tokens") is not None
        else raw_dict.get("total_token_count")
    )

    out: dict[str, int] = {}
    if prompt is not None:
        out["prompt_tokens"] = prompt
    if completion is not None:
        out["completion_tokens"] = completion
    if total is not None:
        out["total_tokens"] = total
    elif prompt is not None and completion is not None:
        out["total_tokens"] = prompt + completion
    return out


def _build_invocation(
    *,
    crew_name: CrewName,
    crew_dir: Path,
    inputs: dict[str, Any],
    context_was_slimmed: bool,
    latency_ms: int | None = None,
    token_usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    from vacation_planner_models import (
        OUTPUT_SCHEMA_VERSION,
        PROMPT_VERSIONS,
        InvocationMeta,
        prompt_hash_for_crew,
    )

    chars = len(json.dumps(inputs, ensure_ascii=False, separators=(",", ":")))
    usage = token_usage or {}
    meta = InvocationMeta(
        crew_name=crew_name,
        prompt_version=PROMPT_VERSIONS.get(crew_name, ""),
        prompt_hash=prompt_hash_for_crew(crew_dir),
        model_id=os.getenv("CREW_MODEL_ID", "bedrock/us.amazon.nova-pro-v1:0"),
        agent_runtime_arn=os.getenv(
            "AGENT_RUNTIME_ARN", os.getenv("AWS_AGENT_RUNTIME_ARN", "")
        ),
        git_sha=os.getenv("GIT_SHA", ""),
        input_context_chars=chars,
        context_was_slimmed=context_was_slimmed,
        output_schema_version=OUTPUT_SCHEMA_VERSION,
        latency_ms=latency_ms,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
    )
    return meta.model_dump(mode="json")


def _wrap_envelope(
    *,
    crew_name: CrewName,
    crew_dir: Path,
    extracted: dict[str, Any],
    inputs: dict[str, Any],
    context_was_slimmed: bool,
    latency_ms: int | None = None,
    token_usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    invocation = _build_invocation(
        crew_name=crew_name,
        crew_dir=crew_dir,
        inputs=inputs,
        context_was_slimmed=context_was_slimmed,
        latency_ms=latency_ms,
        token_usage=token_usage,
    )
    if crew_name in {"day_plan", "day_plan_single"}:
        if "day_plan" in extracted and "quality" in extracted:
            return {
                "result": extracted["day_plan"],
                "quality": extracted["quality"],
                "invocation": invocation,
            }
        return {"result": extracted, "quality": None, "invocation": invocation}
    return {"result": extracted, "quality": None, "invocation": invocation}


def run_crew(crew_name: CrewName, inputs: dict[str, Any]) -> dict[str, Any]:
    """Run a crew and return a CrewEnvelope JSON-ready dict."""
    if crew_name not in _CREW_MODEL_ATTR:
        raise ValueError(
            f"unknown crew_name={crew_name!r}; expected one of {sorted(_CREW_MODEL_ATTR)}"
        )
    crew_dir = crews_root() / crew_name
    if not (crew_dir / "crew.jsonc").is_file():
        raise FileNotFoundError(f"missing crew project at {crew_dir}")

    _load_dotenv_once()
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    (Path.cwd() / "logs").mkdir(parents=True, exist_ok=True)
    (crew_dir / "logs").mkdir(parents=True, exist_ok=True)

    work_inputs = dict(inputs)
    slim_raw = work_inputs.pop(_SLIM_FLAG_KEY, None)
    context_was_slimmed = str(slim_raw).strip().lower() in {"1", "true", "yes"}

    _ensure_import_paths(crew_dir)
    model_cls = _model_class(crew_name)

    from crewai.project import load_crew

    crew, default_inputs = load_crew(crew_dir / "crew.jsonc")
    _disable_llm_stream(crew)
    started = time.perf_counter()
    result = crew.kickoff(inputs={**default_inputs, **work_inputs})
    latency_ms = max(0, int((time.perf_counter() - started) * 1000))
    extracted = extract_pydantic_dict(result, model_cls)
    return _wrap_envelope(
        crew_name=crew_name,
        crew_dir=crew_dir,
        extracted=extracted,
        inputs=work_inputs,
        context_was_slimmed=context_was_slimmed,
        latency_ms=latency_ms,
        token_usage=extract_token_usage(result),
    )


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Kick off a vacation-planner crew")
    parser.add_argument(
        "crew",
        choices=sorted(_CREW_MODEL_ATTR),
        help="Which crew project under agent/crews/",
    )
    parser.add_argument(
        "--inputs-json",
        default="{}",
        help='JSON object merged into crew inputs, e.g. \'{"overnight_city":"Tokyo"}\'',
    )
    args = parser.parse_args()
    try:
        inputs = json.loads(args.inputs_json)
    except json.JSONDecodeError as exc:
        print(f"invalid --inputs-json: {exc}", file=sys.stderr)
        return 2
    if not isinstance(inputs, dict):
        print("--inputs-json must be a JSON object", file=sys.stderr)
        return 2

    if args.crew == "day_plan":
        inputs = {
            "origin": "San Francisco",
            "destination": "Japan",
            "destination_type": "country",
            "day_index": "1",
            "date": "2026-09-01",
            "overnight_city": "Tokyo",
            "preferences": "culture, food, moderate pace",
            "interests": "",
            "energy_level": "3",
            "max_comfortable_minutes": "510",
            "already_visited": "",
            "prior_days_summary": "",
            "city_route_json": "",
            **inputs,
        }
    elif args.crew == "suggest_place":
        inputs = {
            "overnight_city": "Tokyo",
            "day_index": "1",
            "date": "2026-09-01",
            "preferences": "culture, food, moderate pace",
            "interests": "",
            "energy_level": "3",
            "remaining_minutes": "120",
            "already_visited": "",
            "current_places_json": "[]",
            "next_order_in_day": "4",
            **inputs,
        }

    print(f"Running {args.crew}…", flush=True)
    out = run_crew(args.crew, inputs)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
