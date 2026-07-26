"""Day composition balance: food crawl detection and non-food requirements.

Compose-first policy: crews receive ``food_crawl_mode`` / ``min_non_food_places``;
BFF assert is a last-line tripwire (soft energy warnings are separate).
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from http_utils import ApiError
from planning_quality.place_quality import is_food_place

# Explicit crawl / tour phrasing only — bare "food" or "ramen" must NOT match.
_FOOD_CRAWL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bfood\s*crawls?\b",
        r"\brestaurant\s*tours?\b",
        r"\bcafe\s*crawls?\b",
        r"\bcafé\s*crawls?\b",
        r"\bcoffee\s*crawls?\b",
        r"\bbar\s*crawls?\b",
        r"\bpub\s*crawls?\b",
        r"\bizakaya\s*crawls?\b",
        r"\btasting\s*days?\b",
        r"\bfoodie\s*tours?\b",
        r"\beat(?:ing)?\s*tours?\b",
        r"\bculinary\s*tours?\b",
    )
)

# One-off suggest-place hints that clearly ask for a meal / restaurant.
# Keep high-precision: avoid words that often appear as location/atmosphere.
_FOOD_HINT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\blunch\b",
        r"\bdinner\b",
        r"\bbreakfast\b",
        r"\bbrunch\b",
        r"\bsupper\b",
        r"\bmeal\b",
        r"\beat\b",
        r"\beating\b",
        r"\bfood\b",
        r"\brestaurant\b",
        r"\bcafe\b",
        r"\bcafé\b",
        r"\bcoffee\s*shop\b",
        r"\bcoffee\b",
        r"\bramen\b",
        r"\bsushi\b",
        r"\bnoodles?\b",
        r"\bdumplings?\b",
        r"\bdim\s*sum\b",
        r"\bstreet\s*food\b",
        r"\bsnack\b",
        r"\bizakaya\b",
        r"\bbistro\b",
        r"\bbakery\b",
        r"\bdessert\b",
        r"\bcuisine\b",
    )
)

# Cultural / exhibit intent — wins over bare "coffee"/"tea" food matches.
_MUSEUM_HINT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bmuseums?\b",
        r"\bgaller(?:y|ies)\b",
        r"\bexhibition\b",
        r"\bexhibits?\b",
    )
)

# (category, patterns) — first match wins after food/museum resolution.
# Prefer intent words over proximity fillers (near the station, by the bar, …).
_CATEGORY_HINT_PATTERNS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "park",
        tuple(
            re.compile(p, re.IGNORECASE)
            for p in (r"\bparks?\b", r"\bgardens?\b", r"\bgreen\s*space\b")
        ),
    ),
    (
        "museum",
        _MUSEUM_HINT_PATTERNS,
    ),
    (
        "shopping",
        tuple(
            re.compile(p, re.IGNORECASE)
            for p in (
                r"\bshopping\b",
                r"\bbookstores?\b",
                r"\bbook\s*shops?\b",
                r"\bmalls?\b",
                r"\bboutiques?\b",
                r"\bgift\s*shops?\b",
            )
        ),
    ),
    (
        "nightlife",
        tuple(
            re.compile(p, re.IGNORECASE)
            for p in (r"\bnightlife\b", r"\bnight\s*clubs?\b", r"\bcocktail\s*bars?\b")
        ),
    ),
    (
        "nature",
        tuple(
            re.compile(p, re.IGNORECASE)
            for p in (r"\bnature\b", r"\bhikes?\b", r"\btrails?\b", r"\bviewpoint\b")
        ),
    ),
    (
        "transit",
        tuple(
            re.compile(p, re.IGNORECASE)
            for p in (
                r"\btransit\b",
                r"\btrain\s*ride\b",
                r"\bmetro\s*ride\b",
                r"\bsubway\s*ride\b",
            )
        ),
    ),
    (
        "lodging",
        tuple(
            re.compile(p, re.IGNORECASE)
            for p in (
                r"\blodging\b",
                r"\bryokan\b",
                r"\bcheck[\s-]*in\b",
                r"\bhotel\s+(?:stay|room|booking)\b",
            )
        ),
    ),
)


def detect_food_crawl_mode(
    preferences: str,
    interests: Iterable[str] | None = None,
) -> bool:
    """True only when the traveler explicitly asked for a food crawl / tour."""
    parts = [str(preferences or "").strip()]
    if interests:
        parts.extend(str(i).strip() for i in interests if str(i).strip())
    blob = " ".join(parts)
    if not blob:
        return False
    return any(pat.search(blob) for pat in _FOOD_CRAWL_PATTERNS)


def min_non_food_places_for(*, food_crawl_mode: bool) -> int:
    return 0 if food_crawl_mode else 1


def day_shape_hint(
    *,
    food_crawl_mode: bool,
    target_place_count: int = 5,
) -> str:
    if food_crawl_mode:
        return "food_crawl"
    if target_place_count >= 7:
        return "food_activity_activity_activity_activity_activity_food"
    if target_place_count >= 6:
        return "food_activity_activity_activity_activity_food"
    if target_place_count >= 5:
        # Lunch + activities + dinner (meals count toward the total).
        return "food_activity_activity_activity_food"
    if target_place_count >= 4:
        return "food_activity_activity_food"
    return "food_nonfood_food"


def food_count(places: list[dict[str, Any]]) -> int:
    return sum(1 for p in places if is_food_place(p))


def non_food_count(places: list[dict[str, Any]]) -> int:
    return sum(1 for p in places if not is_food_place(p))


def prefer_non_food_suggestion(
    existing: list[dict[str, Any]],
    *,
    food_crawl_mode: bool,
    honor_user_hint: bool = False,
) -> bool:
    """Suggest-place should add a non-food stop when the day still lacks one.

    Only kicks in once the day already has 2+ stops (aligned with the hard
    day-balance gate at 3+ places). A single leftover food stop after delete
    must still allow dinner / another meal. An explicit one-off user hint always
    wins over this balance nudge.
    """
    if honor_user_hint or food_crawl_mode:
        return False
    if len(existing) < 2:
        return False
    return non_food_count(existing) == 0


def detect_food_suggest_hint(hint: str) -> bool:
    """True when the one-off suggest hint clearly asks for a meal / restaurant."""
    text = str(hint or "").strip()
    if not text:
        return False
    return any(pat.search(text) for pat in _FOOD_HINT_PATTERNS)


def infer_suggest_hint_category(hint: str) -> str | None:
    """Map a clear one-off hint to a Place category, or None if ambiguous.

    Uses high-precision phrases only. Proximity fillers like "near the station"
    must not force category=transit and reject otherwise-good venues.
    """
    text = str(hint or "").strip()
    if not text:
        return None
    wants_museum = any(pat.search(text) for pat in _MUSEUM_HINT_PATTERNS)
    wants_food = detect_food_suggest_hint(text)
    # "coffee museum" / "food exhibition" → museum, not food.
    if wants_museum and wants_food:
        return "museum"
    if wants_food:
        return "food"
    if wants_museum:
        return "museum"
    for category, patterns in _CATEGORY_HINT_PATTERNS:
        if category == "museum":
            continue  # already handled
        if any(pat.search(text) for pat in patterns):
            return category
    return None


def day_balance_guidance(*, food_crawl_mode: bool, min_non_food_places: int) -> str:
    """Prepended into crew preferences (survives slim truncation from the end)."""
    if food_crawl_mode:
        return (
            "Day balance: food_crawl_mode=true — a restaurant/cafe-focused day is OK; "
            "still use named venues with street addresses."
        )
    return (
        "Day balance: food_crawl_mode=false — this must feel like a travel day, not a "
        f"restaurant crawl. Include at least {min_non_food_places} non-food Place "
        "(museum, park, shrine/temple, viewpoint, shopping, cultural POI, etc.). "
        "For a 3-stop day prefer food → non-food → food (lunch + activity + dinner). "
        "Food-forward preferences still need non-food stops. Never output food-only days."
    )


def require_day_balance(
    places: list[dict[str, Any]],
    *,
    food_crawl_mode: bool,
    min_non_food_places: int | None = None,
) -> None:
    """Last-line tripwire: reject food-only days unless food crawl."""
    required = (
        min_non_food_places
        if min_non_food_places is not None
        else min_non_food_places_for(food_crawl_mode=food_crawl_mode)
    )
    if required <= 0 or food_crawl_mode:
        return
    if len(places) < 3:
        return
    have = non_food_count(places)
    if have >= required:
        return
    raise ApiError(
        422,
        "day plan needs at least one non-food stop (museum, park, shrine, "
        "shopping, cultural POI, etc.) unless the traveler asked for a food crawl; "
        f"got {have} non-food and {food_count(places)} food",
        code="food_only_day",
    )


def require_suggested_place_balance(
    place: dict[str, Any],
    existing: list[dict[str, Any]],
    *,
    food_crawl_mode: bool,
    honor_user_hint: bool = False,
) -> None:
    """Reject another food stop when the day still has zero non-food."""
    if not prefer_non_food_suggestion(
        existing,
        food_crawl_mode=food_crawl_mode,
        honor_user_hint=honor_user_hint,
    ):
        return
    if not is_food_place(place):
        return
    raise ApiError(
        422,
        "this day still has no non-food stop — suggest a museum, park, shrine, "
        "shopping, or cultural POI instead of another restaurant",
        code="food_only_day",
    )


def require_suggested_place_matches_hint(
    place: dict[str, Any],
    *,
    hint: str,
) -> None:
    """When the hint clearly implies a category, reject obvious mismatches.

    Ambiguous free-text hints are honored via crew guidance + waived balance
    nudge only (no hard category tripwire).
    """
    expected = infer_suggest_hint_category(hint)
    if expected is None:
        return
    if expected == "food":
        if is_food_place(place):
            return
        raise ApiError(
            422,
            "suggestion did not match the user hint",
            code="hint_mismatch",
        )
    actual = str(place.get("category") or "").strip().lower()
    if actual == expected:
        return
    raise ApiError(
        422,
        "suggestion did not match the user hint",
        code="hint_mismatch",
    )
