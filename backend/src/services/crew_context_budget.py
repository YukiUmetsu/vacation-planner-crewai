"""Slim crew inputs only when they exceed a char budget (token proxy).

Hard dedupe / quality still use the full visited set in the BFF. This module only
shrinks advisory prompt fields sent to AgentCore.

Cut order (when over budget):
1. already_visited
2. prior_days_summary
3. city_route_json
4. preferences
"""

from __future__ import annotations

import json
import os
from typing import Any

from db.place_keys import normalize_place_text

# Approximate input budget. already_visited_repeats exists if a crew ever
# interpolates the same list into multiple prompts; keep at 1 when templates
# paste the list only once (research task).
_DEFAULT_MAX_CHARS = 16_000
_ENV_MAX = "CREW_INPUT_MAX_CHARS"


def max_input_chars() -> int:
    raw = os.getenv(_ENV_MAX, "").strip()
    if not raw:
        return _DEFAULT_MAX_CHARS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_CHARS
    return max(1_000, value)


def inputs_char_len(
    inputs: dict[str, Any],
    *,
    already_visited_repeats: int = 1,
) -> int:
    """JSON size of inputs, plus extra copies of already_visited when templates repeat it."""
    base = len(json.dumps(inputs, ensure_ascii=False, separators=(",", ":")))
    repeats = max(1, already_visited_repeats)
    if repeats <= 1:
        return base
    visited = str(inputs.get("already_visited") or "")
    return base + (repeats - 1) * len(visited)


def slim_crew_inputs(
    inputs: dict[str, Any],
    *,
    overnight_city: str = "",
    day_index: int | None = None,
    max_chars: int | None = None,
    already_visited_repeats: int = 1,
) -> dict[str, Any]:
    """
    Return a copy of ``inputs`` that fits ``max_chars`` (effective), or the
    original fields unchanged when already under budget.
    """
    budget = max_chars if max_chars is not None else max_input_chars()
    out = dict(inputs)
    if inputs_char_len(out, already_visited_repeats=already_visited_repeats) <= budget:
        return out

    if "already_visited" in out:
        out["already_visited"] = _slim_already_visited_to_fit(
            out,
            overnight_city=overnight_city,
            budget=budget,
            already_visited_repeats=already_visited_repeats,
        )
        if inputs_char_len(out, already_visited_repeats=already_visited_repeats) <= budget:
            return out

    if "prior_days_summary" in out:
        out["prior_days_summary"] = _slim_prior_days_to_fit(
            out,
            budget=budget,
            already_visited_repeats=already_visited_repeats,
        )
        if inputs_char_len(out, already_visited_repeats=already_visited_repeats) <= budget:
            return out

    if "city_route_json" in out:
        out["city_route_json"] = _slim_city_route_to_fit(
            out,
            overnight_city=overnight_city,
            day_index=day_index,
            budget=budget,
            already_visited_repeats=already_visited_repeats,
        )
        if inputs_char_len(out, already_visited_repeats=already_visited_repeats) <= budget:
            return out

    if "preferences" in out:
        out["preferences"] = _slim_preferences_to_fit(
            out,
            budget=budget,
            already_visited_repeats=already_visited_repeats,
        )

    return out


def _parse_visited_keys(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _key_city_part(place_key: str) -> str:
    if "|" not in place_key:
        return ""
    return place_key.split("|", 1)[1]


def _select_visited_keys(
    keys: list[str],
    *,
    keep_count: int,
    overnight_city: str,
) -> list[str]:
    """Prefer same-city keys, then more recent keys (higher index). Preserve order."""
    if keep_count <= 0:
        return []
    if keep_count >= len(keys):
        return list(keys)

    city_norm = normalize_place_text(overnight_city)
    ranked = sorted(
        range(len(keys)),
        key=lambda i: (
            1
            if city_norm
            and city_norm in normalize_place_text(_key_city_part(keys[i]))
            else 0,
            i,
        ),
        reverse=True,
    )
    chosen_idx = set(ranked[:keep_count])
    return [keys[i] for i in range(len(keys)) if i in chosen_idx]


def _slim_already_visited_to_fit(
    inputs: dict[str, Any],
    *,
    overnight_city: str,
    budget: int,
    already_visited_repeats: int,
) -> str:
    keys = _parse_visited_keys(str(inputs.get("already_visited") or ""))
    if not keys:
        return ""

    lo, hi = 0, len(keys)
    best = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = ",".join(
            _select_visited_keys(keys, keep_count=mid, overnight_city=overnight_city)
        )
        trial = {**inputs, "already_visited": candidate}
        if inputs_char_len(trial, already_visited_repeats=already_visited_repeats) <= budget:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _slim_prior_days_to_fit(
    inputs: dict[str, Any],
    *,
    budget: int,
    already_visited_repeats: int,
) -> str:
    text = str(inputs.get("prior_days_summary") or "")
    if not text:
        return ""
    lines = text.splitlines()
    while lines:
        candidate = "\n".join(lines)
        trial = {**inputs, "prior_days_summary": candidate}
        if inputs_char_len(trial, already_visited_repeats=already_visited_repeats) <= budget:
            return candidate
        lines = lines[1:]
    return ""


def _minimal_route_json(overnight_city: str, day_index: int | None) -> str:
    city = overnight_city.strip() or "unknown"
    day = day_index if day_index is not None else 1
    payload = {
        "cities": [
            {
                "city": city,
                "arrival_day_index": day,
                "departure_day_index": day,
                "nights": 0,
            }
        ],
        "total_nights": 0,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _windowed_route_json(
    raw: str,
    *,
    overnight_city: str,
    day_index: int | None,
) -> str:
    """Keep cities covering day_index (±0) or matching overnight; else overnight stub."""
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return _minimal_route_json(overnight_city, day_index)
    if not isinstance(data, dict):
        return _minimal_route_json(overnight_city, day_index)

    cities = data.get("cities")
    if not isinstance(cities, list):
        return _minimal_route_json(overnight_city, day_index)

    city_norm = normalize_place_text(overnight_city)
    kept: list[Any] = []
    for stop in cities:
        if not isinstance(stop, dict):
            continue
        name = str(stop.get("city") or "")
        if city_norm and normalize_place_text(name) == city_norm:
            kept.append(stop)
            continue
        if day_index is None:
            continue
        arrival = int(stop.get("arrival_day_index") or 0)
        departure = int(stop.get("departure_day_index") or 0)
        if arrival <= day_index <= departure:
            kept.append(stop)

    if not kept:
        return _minimal_route_json(overnight_city, day_index)

    nights_sum = sum(int(c.get("nights") or 0) for c in kept if isinstance(c, dict))
    slim = {**data, "cities": kept, "total_nights": nights_sum}
    # Drop bulky optional prose fields if present
    for key in ("summary", "rationale", "notes", "overview"):
        slim.pop(key, None)
    return json.dumps(slim, ensure_ascii=False, separators=(",", ":"))


def _slim_city_route_to_fit(
    inputs: dict[str, Any],
    *,
    overnight_city: str,
    day_index: int | None,
    budget: int,
    already_visited_repeats: int,
) -> str:
    raw = str(inputs.get("city_route_json") or "")
    if not raw:
        return ""

    windowed = _windowed_route_json(
        raw, overnight_city=overnight_city, day_index=day_index
    )
    trial = {**inputs, "city_route_json": windowed}
    if inputs_char_len(trial, already_visited_repeats=already_visited_repeats) <= budget:
        return windowed

    minimal = _minimal_route_json(overnight_city, day_index)
    trial_min = {**inputs, "city_route_json": minimal}
    if inputs_char_len(trial_min, already_visited_repeats=already_visited_repeats) <= budget:
        return minimal
    return ""


def _slim_preferences_to_fit(
    inputs: dict[str, Any],
    *,
    budget: int,
    already_visited_repeats: int,
) -> str:
    text = str(inputs.get("preferences") or "")
    if not text:
        return ""

    lo, hi = 0, len(text)
    best = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = text[:mid].rstrip()
        trial = {**inputs, "preferences": candidate}
        if inputs_char_len(trial, already_visited_repeats=already_visited_repeats) <= budget:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best
