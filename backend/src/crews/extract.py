"""Extract structured outputs from CrewAI kickoff results."""

from __future__ import annotations

from typing import Any


def extract_pydantic_dict(result: Any, model_cls: type) -> dict[str, Any]:
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
            return model_cls.model_validate_json(raw[start : end + 1]).model_dump(mode="json")
        raise
