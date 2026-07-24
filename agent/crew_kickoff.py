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
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

CrewName = Literal["day_plan", "city_route", "suggest_place"]

_CREW_MODEL_ATTR: dict[CrewName, str] = {
    "day_plan": "DayPlanWithQuality",
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
    _ensure_serper_from_secrets()


def _ensure_serper_from_secrets() -> None:
    """If SERPER_API_KEY unset, load from SERPER_SECRET_ARN (AgentCore / AWS)."""
    if os.getenv("SERPER_API_KEY", "").strip():
        return
    secret_id = os.getenv("SERPER_SECRET_ARN", "").strip()
    if not secret_id:
        return
    try:
        import boto3
    except ImportError:
        return
    try:
        raw = (
            boto3.client("secretsmanager")
            .get_secret_value(SecretId=secret_id)
            .get("SecretString")
            or ""
        )
    except Exception:
        return
    if not isinstance(raw, str) or not raw.strip():
        return
    value = raw.strip()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        os.environ["SERPER_API_KEY"] = value
        return
    if isinstance(parsed, dict):
        for key in ("api_key", "SERPER_API_KEY", "key", "value", "secret"):
            cand = parsed.get(key)
            if isinstance(cand, str) and cand.strip():
                os.environ["SERPER_API_KEY"] = cand.strip()
                return
    os.environ["SERPER_API_KEY"] = value


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

    if crew_name == "day_plan":
        return DayPlanWithQuality
    if crew_name == "suggest_place":
        return Place
    return CityRoute


def _build_invocation(
    *,
    crew_name: CrewName,
    crew_dir: Path,
    inputs: dict[str, Any],
    context_was_slimmed: bool,
) -> dict[str, Any]:
    from vacation_planner_models import (
        OUTPUT_SCHEMA_VERSION,
        PROMPT_VERSIONS,
        InvocationMeta,
        prompt_hash_for_crew,
    )

    chars = len(json.dumps(inputs, ensure_ascii=False, separators=(",", ":")))
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
    )
    return meta.model_dump(mode="json")


def _wrap_envelope(
    *,
    crew_name: CrewName,
    crew_dir: Path,
    extracted: dict[str, Any],
    inputs: dict[str, Any],
    context_was_slimmed: bool,
) -> dict[str, Any]:
    invocation = _build_invocation(
        crew_name=crew_name,
        crew_dir=crew_dir,
        inputs=inputs,
        context_was_slimmed=context_was_slimmed,
    )
    if crew_name == "day_plan":
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
    result = crew.kickoff(inputs={**default_inputs, **work_inputs})
    extracted = extract_pydantic_dict(result, model_cls)
    return _wrap_envelope(
        crew_name=crew_name,
        crew_dir=crew_dir,
        extracted=extracted,
        inputs=work_inputs,
        context_was_slimmed=context_was_slimmed,
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
