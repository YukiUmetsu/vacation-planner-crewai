"""Plan-next-day LLM retries after BFF quality / dedupe failures.

Up to three attempts (base + two recovery edits). Each retry prepends guidance
and bans only places that were actually rejected (closed / visited / deduped),
then re-invokes the crew. Meal / day-balance failures do not ban usable stops.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from services.dedupe import ensure_place_key
from services.place_quality import (
    is_closed_on_date,
    is_permanently_closed,
    place_matches_visited_name,
)

# Failures that usually improve if the model proposes different venues.
RETRYABLE_PLAN_DAY_CODES: frozenset[str] = frozenset(
    {
        "quality_empty",
        "dedupe_empty",
        "missing_meals",
        "food_only_day",
    }
)

# Composition failures: keep prior open venues; ask the model to fix shape.
_COMPOSITION_RETRY_CODES: frozenset[str] = frozenset(
    {"missing_meals", "food_only_day"}
)

MAX_PLAN_DAY_ATTEMPTS = 3


def place_labels(places: list[dict[str, Any]]) -> list[str]:
    """Stable unique place names from a failed crew day."""
    out: list[str] = []
    seen: set[str] = set()
    for place in places:
        name = str(place.get("name") or "").strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def merge_banned_labels(*batches: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for batch in batches:
        for name in batch:
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(name)
    return out


def rejected_quality_labels(
    places: list[dict[str, Any]],
    *,
    plan_date: date,
    profile_visited_names: set[str] | None = None,
) -> list[str]:
    """Names dropped by closed / weekday-closed / profile-visited filters."""
    visited_names = profile_visited_names or set()
    rejected: list[dict[str, Any]] = []
    for place in places:
        enriched = {**place, "place_key": ensure_place_key(place)}
        if is_permanently_closed(enriched):
            rejected.append(enriched)
            continue
        if is_closed_on_date(enriched, plan_date):
            rejected.append(enriched)
            continue
        if place_matches_visited_name(enriched, visited_names):
            rejected.append(enriched)
    return place_labels(rejected)


def labels_to_ban_after_failure(
    *,
    code: str | None,
    places: list[dict[str, Any]],
    plan_date: date,
    profile_visited_names: set[str] | None = None,
) -> list[str]:
    """Which place names to ban on the next LLM attempt for ``code``."""
    failure = str(code or "")
    if failure in _COMPOSITION_RETRY_CODES:
        # Usable stops already passed closed/visited filters — do not ban them.
        return []
    if failure == "quality_empty":
        return rejected_quality_labels(
            places,
            plan_date=plan_date,
            profile_visited_names=profile_visited_names,
        )
    if failure == "dedupe_empty":
        return place_labels(places)
    return []


def apply_plan_day_retry_inputs(
    inputs: dict[str, Any],
    *,
    attempt: int,
    failure_code: str | None,
    banned_places: list[str],
) -> dict[str, Any]:
    """Return crew inputs for ``attempt`` (0 = first try, no edit).

    Attempt 1 — ban rejected places + stress open / non-visited venues.
    Attempt 2 — expand geography + meals/non-food rules + stronger ban list.
    Each attempt starts from the original base inputs (hints do not stack).
    """
    if attempt <= 0:
        return dict(inputs)

    overnight = str(inputs.get("overnight_city") or "the city").strip() or "the city"
    banned = ", ".join(banned_places) if banned_places else "(none listed)"
    code = (failure_code or "quality").strip() or "quality"

    if attempt == 1:
        if code in _COMPOSITION_RETRY_CODES:
            hint = (
                f"RETRY ({code}): previous day failed meal/day-balance checks. "
                f"Keep the overnight city ({overnight}). Fix composition: "
                "include lunch + dinner food stops (and breakfast when "
                "include_breakfast=true), and at least one non-food place "
                "unless food_crawl_mode=true. Prefer currently open venues."
            )
        else:
            hint = (
                f"RETRY ({code}): previous day plan failed BFF checks. "
                f"Do NOT reuse these rejected places: {banned}. "
                f"Propose at least 3 currently open venues in {overnight} with "
                "street addresses. Respect already_visited. Prefer well-known "
                "operating attractions and restaurants — never permanently "
                "closed businesses."
            )
    else:
        if code in _COMPOSITION_RETRY_CODES:
            hint = (
                f"FINAL RETRY ({code}): still need meals / day balance in "
                f"{overnight}. Include lunch + dinner "
                "(+ breakfast when include_breakfast=true) and ≥1 non-food "
                "stop unless food_crawl_mode=true. Different neighborhoods OK."
            )
        else:
            hint = (
                f"FINAL RETRY ({code}): still need a valid day in {overnight}. "
                f"Banned rejected places (do not reuse): {banned}. "
                "Pick different neighborhoods or districts. Include required "
                "meals and at least one non-food stop unless "
                "food_crawl_mode=true. Aim for target_place_count or more "
                "open candidates."
            )
        try:
            target = int(str(inputs.get("target_place_count") or "5"))
        except ValueError:
            target = 5
        inputs = {
            **inputs,
            "target_place_count": str(min(target + 2, 7)),
        }

    prefs = str(inputs.get("preferences") or "").strip()
    merged = f"{hint} | {prefs}".strip(" |") if prefs else hint
    return {**inputs, "preferences": merged}


def should_retry_plan_day(*, code: str | None, attempt: int) -> bool:
    """True when another LLM attempt is warranted."""
    if attempt + 1 >= MAX_PLAN_DAY_ATTEMPTS:
        return False
    return str(code or "") in RETRYABLE_PLAN_DAY_CODES
