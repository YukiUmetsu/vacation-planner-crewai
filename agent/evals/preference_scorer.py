"""Pluggable preference relevance scorers (heuristic default, LLM-as-judge optional).

Same metric key: ``preference_relevance_score`` (0–1).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Protocol

from evals.case import EvalCase
from evals.scorers import _as_lower_token_list


class PreferenceScorer(Protocol):
    def score_preference_relevance(
        self, output: dict[str, Any], case: EvalCase
    ) -> float: ...


def interests_for_case(case: EvalCase) -> list[str]:
    interests = _as_lower_token_list(case.expected.get("interests"))
    if not interests:
        interests = _as_lower_token_list(case.inputs.get("interests"))
    return interests


def excluded_categories_for_case(case: EvalCase) -> list[str]:
    excluded = _as_lower_token_list(case.expected.get("excluded_categories"))
    if not excluded:
        excluded = _as_lower_token_list(case.inputs.get("excluded_categories"))
    return excluded


def places_blob(places: list[Any]) -> str:
    return " ".join(
        str(place.get(field) or "")
        for place in places
        if isinstance(place, dict)
        for field in ("name", "reason_to_visit", "details", "category")
    ).lower()


class HeuristicPreferenceScorer:
    """Deterministic interest/category keyword overlap (MVP default)."""

    def score_preference_relevance(
        self, output: dict[str, Any], case: EvalCase
    ) -> float:
        places = output.get("places") if isinstance(output.get("places"), list) else []
        interests = interests_for_case(case)
        if not interests:
            return 1.0
        blob = places_blob(places)
        hits = sum(1 for interest in interests if interest in blob)
        return float(hits / max(1, len(interests)))


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _parse_judge_json(text: str) -> float | None:
    """Extract preference_relevance_score from model text."""
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "preference_relevance_score" in data:
            return _clamp01(float(data["preference_relevance_score"]))
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    match = re.search(r"\{[^{}]*preference_relevance_score[^{}]*\}", text, re.I)
    if match:
        try:
            data = json.loads(match.group(0))
            return _clamp01(float(data["preference_relevance_score"]))
        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
            return None
    return None


InvokeFn = Callable[[str], str]


class LlmPreferenceScorer:
    """Bedrock (or injectable) LLM judge for preference_relevance_score only.

    Falls back to ``HeuristicPreferenceScorer`` when the model call fails or
    returns unparseable output. Offline CI stays hermetic via ``invoke``.
    """

    def __init__(
        self,
        *,
        invoke: InvokeFn | None = None,
        model_id: str | None = None,
        fallback: PreferenceScorer | None = None,
    ) -> None:
        self._invoke = invoke
        self._model_id = (
            model_id
            or os.getenv("EVAL_JUDGE_MODEL_ID")
            or os.getenv("CREW_MODEL_ID", "us.amazon.nova-lite-v1:0")
        ).removeprefix("bedrock/")
        self._fallback = fallback or HeuristicPreferenceScorer()

    def score_preference_relevance(
        self, output: dict[str, Any], case: EvalCase
    ) -> float:
        try:
            prompt = self._build_prompt(output, case)
            raw = (self._invoke or self._bedrock_invoke)(prompt)
            parsed = _parse_judge_json(raw)
            if parsed is not None:
                return parsed
        except Exception:  # noqa: BLE001 — eval boundary; never fail the suite hard
            pass
        return self._fallback.score_preference_relevance(output, case)

    def _build_prompt(self, output: dict[str, Any], case: EvalCase) -> str:
        places = output.get("places") if isinstance(output.get("places"), list) else []
        compact = [
            {
                "name": p.get("name"),
                "category": p.get("category"),
                "reason_to_visit": p.get("reason_to_visit"),
            }
            for p in places
            if isinstance(p, dict)
        ]
        payload = {
            "interests": interests_for_case(case),
            "excluded_categories": excluded_categories_for_case(case),
            "preferences": case.inputs.get("preferences") or "",
            "places": compact,
        }
        return (
            "Score how well this day plan matches traveler interests/preferences.\n"
            "Return ONLY JSON: "
            '{"preference_relevance_score": <float 0..1>, "notes": "<short>"}\n'
            "0 = no match, 1 = strong match. Penalize excluded_categories if present.\n\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

    def _bedrock_invoke(self, prompt: str) -> str:
        import boto3

        client = boto3.client("bedrock-runtime")
        response = client.converse(
            modelId=self._model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 256, "temperature": 0},
        )
        parts = response.get("output", {}).get("message", {}).get("content") or []
        texts = [str(p.get("text") or "") for p in parts if isinstance(p, dict)]
        return "\n".join(t for t in texts if t).strip()


def resolve_preference_scorer(name: str) -> PreferenceScorer:
    key = (name or "heuristic").strip().lower()
    if key in ("heuristic", "default", ""):
        return HeuristicPreferenceScorer()
    if key in ("llm", "judge", "llm-judge"):
        return LlmPreferenceScorer()
    raise ValueError(
        f"unknown preference judge {name!r}; use heuristic or llm"
    )
