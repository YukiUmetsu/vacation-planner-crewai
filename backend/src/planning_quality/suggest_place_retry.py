"""Suggest-place LLM retries after BFF closed / weekday quality failures.

Up to three attempts (base + two recovery edits). Each retry bans the rejected
venue and prepends failure-specific open-venue guidance before re-invoking.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from planning_quality.dedupe import ensure_place_key

# Failures that usually improve if the model picks a different venue.
RETRYABLE_SUGGEST_PLACE_CODES: frozenset[str] = frozenset(
    {
        "place_weekday_closed",
        "place_closed",
        "place_duplicate",
        "hint_mismatch",
    }
)

MAX_SUGGEST_PLACE_ATTEMPTS = 3

_WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def should_retry_suggest_place(*, code: str | None, attempt: int) -> bool:
    """True when another crew attempt is warranted (attempt is 0-based)."""
    if attempt + 1 >= MAX_SUGGEST_PLACE_ATTEMPTS:
        return False
    return str(code or "") in RETRYABLE_SUGGEST_PLACE_CODES


def rejected_suggest_labels(place: dict[str, Any] | None) -> list[str]:
    """Stable unique names / keys to ban on the next suggest attempt."""
    if not isinstance(place, dict):
        return []
    out: list[str] = []
    seen: set[str] = set()
    place_id = str(place.get("place_id") or "").strip()
    for raw in (
        place.get("name"),
        place.get("place_key"),
        ensure_place_key(place),
        place_id or None,
    ):
        label = str(raw or "").strip()
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(label)
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


def _retry_hint(
    *,
    attempt: int,
    failure_code: str,
    plan_date: date,
    banned: str,
    user_hint: str = "",
) -> str:
    weekday = plan_date.weekday()
    weekday_name = _WEEKDAY_NAMES[weekday]
    date_s = plan_date.isoformat()
    final = attempt >= 2
    prefix = "FINAL RETRY" if final else "RETRY"
    hint_label = user_hint.strip() or "(see preferences)"

    if failure_code == "place_closed":
        if final:
            return (
                f"{prefix} (place_closed): still need a currently operating venue. "
                f"Banned: {banned}. Do not suggest permanently closed businesses."
            )
        return (
            f"{prefix} (place_closed): previous suggestion was permanently closed. "
            f"Do NOT reuse: {banned}. Pick a different currently operating venue."
        )

    if failure_code == "place_duplicate":
        if final:
            return (
                f"{prefix} (place_duplicate): still need a new place for {date_s}. "
                f"Banned: {banned}. Choose a different name/neighborhood."
            )
        return (
            f"{prefix} (place_duplicate): previous suggestion was already used. "
            f"Do NOT reuse: {banned}. Pick a different venue."
        )

    if failure_code == "hint_mismatch":
        if final:
            return (
                f"{prefix} (hint_mismatch): still must match user hint {hint_label!r}. "
                f"Banned: {banned}. Pick a venue that clearly fits that request."
            )
        return (
            f"{prefix} (hint_mismatch): previous pick ignored user hint "
            f"{hint_label!r}. Do NOT reuse: {banned}. Match that hint "
            "(and preferred category if stated) — do not substitute an unrelated POI."
        )

    # Default: weekday / unknown closed-on-date failures.
    if final:
        return (
            f"{prefix} (place_weekday_closed): still need a place open on "
            f"{weekday_name} ({date_s}, weekday={weekday}). Banned: {banned}. "
            "Choose a well-known operating attraction or restaurant with "
            "different name/neighborhood — never permanently closed or "
            f"closed_weekdays containing {weekday}."
        )
    return (
        f"{prefix} (place_weekday_closed): previous suggestion was closed for "
        f"{date_s} ({weekday_name}, weekday={weekday}). Do NOT reuse: {banned}. "
        f"Pick a different currently open venue that is open on {weekday_name} "
        f"(closed_weekdays must not include {weekday})."
    )


def apply_suggest_place_retry_inputs(
    inputs: dict[str, Any],
    *,
    attempt: int,
    failure_code: str | None,
    plan_date: date,
    banned_places: list[str],
) -> dict[str, Any]:
    """Return crew inputs for ``attempt`` (0 = first try, no edit).

    Each retry starts from the original base inputs (hints do not stack).
    """
    if attempt <= 0:
        return dict(inputs)

    banned = ", ".join(banned_places) if banned_places else "(none listed)"
    code = (failure_code or "place_weekday_closed").strip() or "place_weekday_closed"
    hint = _retry_hint(
        attempt=attempt,
        failure_code=code,
        plan_date=plan_date,
        banned=banned,
        user_hint=str(inputs.get("hint") or ""),
    )

    prefs = str(inputs.get("preferences") or "").strip()
    merged = f"{hint} | {prefs}".strip(" |") if prefs else hint

    visited = str(inputs.get("already_visited") or "").strip()
    ban_keys = [b for b in banned_places if b]
    if ban_keys:
        extra = ",".join(ban_keys)
        visited = f"{visited},{extra}".strip(",") if visited else extra

    return {**inputs, "preferences": merged, "already_visited": visited}
