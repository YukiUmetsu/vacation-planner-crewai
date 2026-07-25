"""Token → USD cost helpers for offline eval reports.

Rates are approximate published Bedrock on-demand prices for Nova Pro
(US, per 1K tokens). Update when AWS pricing changes.
"""

from __future__ import annotations

from typing import Any

# bedrock/us.amazon.nova-pro-v1:0 approximate USD per 1K tokens
_NOVA_PRO_INPUT_PER_1K = 0.0008
_NOVA_PRO_OUTPUT_PER_1K = 0.0032


def estimate_cost_usd(invocation: dict[str, Any] | None) -> float | None:
    """Estimate USD cost from invocation token fields. None if tokens missing."""
    inv = invocation or {}
    prompt = inv.get("prompt_tokens")
    completion = inv.get("completion_tokens")
    total = inv.get("total_tokens")
    try:
        p = int(prompt) if prompt is not None else None
        c = int(completion) if completion is not None else None
        t = int(total) if total is not None else None
    except (TypeError, ValueError):
        return None
    if p is None and c is None and t is None:
        return None
    if p is None and c is None and t is not None:
        # Unknown split — charge all as input (conservative lower bound).
        return round((t / 1000.0) * _NOVA_PRO_INPUT_PER_1K, 6)
    p = p or 0
    c = c or 0
    return round(
        (p / 1000.0) * _NOVA_PRO_INPUT_PER_1K
        + (c / 1000.0) * _NOVA_PRO_OUTPUT_PER_1K,
        6,
    )
