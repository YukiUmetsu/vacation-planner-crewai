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

CrewName = Literal[
    "day_plan",
    "day_plan_single",
    "city_route",
    "suggest_place",
    "suggest_city",
]

_CREW_MODEL_ATTR: dict[CrewName, str] = {
    "day_plan": "DayPlanWithQuality",
    "day_plan_single": "DayPlanWithQuality",
    "city_route": "CityRoute",
    "suggest_place": "Place",
    "suggest_city": "CitySuggestionResult",
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


def _configure_nova_friendly_llms(crew: Any) -> None:
    """Prefer greedy decoding + enough completion tokens for Bedrock Nova ToolUse.

    AWS docs: temperature=0 (and topK=1) reduces invalid ToolUse sequences;
    truncated tool calls from a low maxTokens also trigger ModelErrorException.
    """
    try:
        temperature = float(os.getenv("CREW_LLM_TEMPERATURE", "0"))
    except ValueError:
        temperature = 0.0
    try:
        max_tokens = int(os.getenv("CREW_LLM_MAX_TOKENS", "4096"))
    except ValueError:
        max_tokens = 4096
    max_tokens = max(512, max_tokens)

    llms: list[Any] = []
    for agent in getattr(crew, "agents", None) or []:
        llm = getattr(agent, "llm", None)
        if llm is not None:
            llms.append(llm)
    for attr in ("function_calling_llm", "manager_llm"):
        llm = getattr(crew, attr, None)
        if llm is not None:
            llms.append(llm)

    for llm in llms:
        for key, value in (
            ("temperature", temperature),
            ("max_tokens", max_tokens),
            ("max_completion_tokens", max_tokens),
        ):
            if hasattr(llm, key):
                try:
                    setattr(llm, key, value)
                except Exception:  # noqa: BLE001
                    pass
        # LiteLLM / Bedrock extra body (best-effort).
        for extra_attr in ("additional_model_request_fields", "model_kwargs"):
            extra = getattr(llm, extra_attr, None)
            if not isinstance(extra, dict):
                continue
            try:
                inference = dict(extra.get("inferenceConfig") or {})
                inference["temperature"] = temperature
                inference["maxTokens"] = max_tokens
                extra["inferenceConfig"] = inference
                # Nova greedy tip (topK=1) when the field dict is used.
                extra.setdefault("topK", 1)
            except Exception:  # noqa: BLE001
                pass


def _is_bedrock_tooluse_error(exc: BaseException) -> bool:
    """True only for Nova/Bedrock malformed ToolUse failures (retryable)."""
    needles = (
        "invalid sequence as part of tooluse",
        "model produced invalid sequence",
        "modelerrorexception",
    )
    cur: BaseException | None = exc
    for _ in range(8):
        if cur is None:
            break
        blob = f"{type(cur).__name__}: {cur}".lower()
        if any(n in blob for n in needles):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def _tooluse_retry_attempts() -> int:
    """Total kickoff attempts when ToolUse fails (1 = no retry)."""
    raw = os.getenv("CREW_TOOLUSE_RETRIES", "2").strip()
    try:
        # retries after first try → attempts = retries + 1
        retries = int(raw)
    except ValueError:
        retries = 2
    return max(1, min(retries, 5) + 1)


def _evals_quiet_enabled() -> bool:
    flag = os.getenv("EVALS_QUIET", "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    return os.getenv("CREW_VERBOSE", "").strip().lower() in {"0", "false", "no", "off"}


def _silence_crew_console(crew: Any) -> None:
    """Disable CrewAI verbose panels / tracing for eval or CREW_VERBOSE=0 runs."""
    if not _evals_quiet_enabled():
        return
    try:
        crew.verbose = False
    except Exception:  # noqa: BLE001
        pass
    try:
        crew.tracing = False
    except Exception:  # noqa: BLE001
        pass
    for agent in getattr(crew, "agents", None) or []:
        try:
            agent.verbose = False
        except Exception:  # noqa: BLE001
            pass


class _DiscardingTextIO:
    """Stdout sink that drops CrewAI/rich spam without touching stderr."""

    encoding = "utf-8"

    def write(self, data: Any) -> int:
        if data is None:
            return 0
        if isinstance(data, (bytes, bytearray)):
            return len(data)
        return len(str(data))

    def writelines(self, lines: Any) -> None:
        for line in lines or []:
            self.write(line)

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return False

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def fileno(self) -> int:
        raise OSError("no fileno for discarding stdout")


_QUIET_STDOUT_INSTALLED = False
_REAL_STDOUT: Any = None
_QUIET_TRACING_INSTALLED = False


def install_quiet_stdout() -> None:
    """Replace ``sys.stdout`` once for the process (thread-safe for parallel arms).

    Per-kickoff ``redirect_stdout`` races across threads and can leave the real
    stdout pointing at a dead ``StringIO``, which swallows later progress/summary
    prints. Progress must use stderr; install this before parallel crew runs.
    """
    global _QUIET_STDOUT_INSTALLED, _REAL_STDOUT
    if not _evals_quiet_enabled() or _QUIET_STDOUT_INSTALLED:
        return
    _REAL_STDOUT = sys.stdout
    sys.stdout = _DiscardingTextIO()
    _QUIET_STDOUT_INSTALLED = True


def restore_quiet_stdout() -> None:
    """Restore the real stdout after a quiet eval run (optional)."""
    global _QUIET_STDOUT_INSTALLED, _REAL_STDOUT
    if not _QUIET_STDOUT_INSTALLED:
        return
    if _REAL_STDOUT is not None:
        sys.stdout = _REAL_STDOUT
    _REAL_STDOUT = None
    _QUIET_STDOUT_INSTALLED = False


def install_quiet_crewai_tracing() -> None:
    """Hard-disable CrewAI tracing UI during quiet evals.

    CrewAI's ``CREWAI_TRACING_ENABLED=false`` does **not** override prior user
    consent, and ``Trace Batch Finalization`` panels print on stderr without
    checking ``should_suppress_tracing_messages``. This installs process-wide
    patches so quiet runs stay silent.
    """
    global _QUIET_TRACING_INSTALLED
    if not _evals_quiet_enabled() or _QUIET_TRACING_INSTALLED:
        return

    os.environ["CREWAI_TRACING_ENABLED"] = "false"
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    # Skip interactive first-time / trace-view prompts.
    os.environ.setdefault("CREWAI_TESTING", "true")

    try:
        from crewai.events.listeners.tracing import utils as tracing_utils
        from crewai.events.listeners.tracing.trace_batch_manager import (
            TraceBatchManager,
        )
        from rich.console import Console
        from rich.panel import Panel
    except Exception:  # noqa: BLE001
        return

    tracing_utils.set_tracing_enabled(False)
    tracing_utils.set_suppress_tracing_messages(True)

    if not getattr(tracing_utils, "_vacation_planner_quiet_should_enable", False):
        _orig_should_enable = tracing_utils.should_enable_tracing

        def _should_enable_tracing(*, override: bool | None = None) -> bool:
            if override is True:
                return True
            if override is False:
                return False
            env = os.getenv("CREWAI_TRACING_ENABLED", "").strip().lower()
            if env in {"false", "0", "no", "off"}:
                return False
            return bool(_orig_should_enable(override=override))

        tracing_utils.should_enable_tracing = _should_enable_tracing  # type: ignore[method-assign]
        tracing_utils._vacation_planner_quiet_should_enable = True

    if not getattr(Console, "_vacation_planner_quiet_print", False):
        _orig_print = Console.print

        def _quiet_print(self: Any, *args: Any, **kwargs: Any) -> Any:
            if tracing_utils.should_suppress_tracing_messages():
                for arg in args:
                    blob = ""
                    if isinstance(arg, Panel):
                        blob = f"{getattr(arg, 'title', '')} {arg}"
                    else:
                        blob = str(arg)
                    if any(
                        needle in blob
                        for needle in (
                            "Trace Batch Finalization",
                            "Trace Batch",
                            "Tracing Status",
                            "Tracing Preference",
                            "Execution Traces",
                        )
                    ):
                        return None
            return _orig_print(self, *args, **kwargs)

        Console.print = _quiet_print  # type: ignore[method-assign]
        Console._vacation_planner_quiet_print = True

    if not getattr(TraceBatchManager, "_vacation_planner_quiet_finalize", False):
        _orig_finalize = TraceBatchManager._finalize_backend_batch

        def _quiet_finalize(self: Any, events_count: int = 0) -> bool:
            # Event-bus threads may not inherit the suppress ContextVar.
            tracing_utils.set_suppress_tracing_messages(True)
            return bool(_orig_finalize(self, events_count))

        TraceBatchManager._finalize_backend_batch = _quiet_finalize  # type: ignore[method-assign]
        TraceBatchManager._vacation_planner_quiet_finalize = True

    _QUIET_TRACING_INSTALLED = True


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
    from vacation_planner_models import (
        CityRoute,
        CitySuggestionResult,
        DayPlanWithQuality,
        Place,
    )

    if crew_name in {"day_plan", "day_plan_single"}:
        return DayPlanWithQuality
    if crew_name == "suggest_place":
        return Place
    if crew_name == "suggest_city":
        return CitySuggestionResult
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
    if _evals_quiet_enabled():
        install_quiet_crewai_tracing()
    (Path.cwd() / "logs").mkdir(parents=True, exist_ok=True)
    (crew_dir / "logs").mkdir(parents=True, exist_ok=True)

    work_inputs = dict(inputs)
    slim_raw = work_inputs.pop(_SLIM_FLAG_KEY, None)
    context_was_slimmed = str(slim_raw).strip().lower() in {"1", "true", "yes"}

    _ensure_import_paths(crew_dir)
    model_cls = _model_class(crew_name)

    from crewai.project import load_crew

    # Install tracing patches before Crew construction (model validator enables tracing).
    if _evals_quiet_enabled():
        install_quiet_crewai_tracing()

    crew, default_inputs = load_crew(crew_dir / "crew.jsonc")
    _disable_llm_stream(crew)
    _configure_nova_friendly_llms(crew)
    _silence_crew_console(crew)
    # Install once (not per-kickoff redirect): parallel arms share one sink.
    install_quiet_stdout()
    if _evals_quiet_enabled():
        install_quiet_crewai_tracing()
        try:
            from crewai.events.listeners.tracing.utils import (
                set_suppress_tracing_messages,
                set_tracing_enabled,
            )

            set_tracing_enabled(False)
            set_suppress_tracing_messages(True)
        except Exception:  # noqa: BLE001
            pass

    merged_inputs = {**default_inputs, **work_inputs}
    attempts = _tooluse_retry_attempts()
    started = time.perf_counter()
    result: Any = None
    extracted: dict[str, Any] | None = None

    for attempt in range(1, attempts + 1):
        try:
            if _evals_quiet_enabled():
                import logging

                prev_level = logging.root.level
                logging.root.setLevel(logging.CRITICAL)
                try:
                    result = crew.kickoff(inputs=merged_inputs)
                finally:
                    logging.root.setLevel(prev_level)
            else:
                result = crew.kickoff(inputs=merged_inputs)
            # Structured-output conversion can also raise ToolUse ModelErrors.
            extracted = extract_pydantic_dict(result, model_cls)
            break
        except Exception as exc:  # noqa: BLE001
            if _is_bedrock_tooluse_error(exc) and attempt < attempts:
                print(
                    f"crew={crew_name} ToolUse error (attempt {attempt}/{attempts}); "
                    f"retrying… ({type(exc).__name__})",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(min(2.0 * attempt, 6.0))
                continue
            raise

    if extracted is None or result is None:
        raise RuntimeError(f"crew={crew_name} produced no result after ToolUse retries")

    latency_ms = max(0, int((time.perf_counter() - started) * 1000))
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
            "hint": "",
            "interests": "",
            "energy_level": "3",
            "remaining_minutes": "120",
            "already_visited": "",
            "current_places_json": "[]",
            "next_order_in_day": "4",
            **inputs,
        }
    elif args.crew == "suggest_city":
        inputs = {
            "destination": "Japan",
            "destination_type": "country",
            "origin": "San Francisco",
            "day_count": "7",
            "start_date": "2026-09-01",
            "end_date": "2026-09-07",
            "preferences": "culture, food, moderate pace",
            "interests": "",
            "hint": "",
            "count": "1",
            "already_listed_cities": "Tokyo, Kyoto",
            "current_cities_json": "[]",
            **inputs,
        }

    print(f"Running {args.crew}…", flush=True)
    out = run_crew(args.crew, inputs)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
