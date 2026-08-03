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
# Food matching uses these phrases; clear non-food categories and substantive
# free-text hints reject food; proximity/vibe-only hints stay ambiguous.
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
        r"\bpizzas?\b",
        r"\btacos?\b",
        r"\bburgers?\b",
        r"\bpasta\b",
        r"\bsteaks?\b",
        r"\bseafood\b",
        r"\bpho\b",
        r"\bcurry\b",
        r"\btapas\b",
        r"\bsandwiches?\b",
        r"\bpastr(?:y|ies)\b",
        r"\bgelatos?\b",
        r"\bice\s*creams?\b",
        r"\byakitori\b",
        r"\btempura\b",
        r"\budon\b",
        r"\bsoba\b",
        r"\bgyoza\b",
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


# Location / vibe fillers — alone they do not force non-food (ambiguous hint).
_LOCATION_VIBE_FILLER_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bnear(?:by)?\b",
        r"\bclose\s+to\b",
        r"\bclose\s*by\b",
        r"\bby\s+the\b",
        r"\baround(?:\s+the)?\b",
        r"\bwithin\s+walking\s+distance\b",
        r"\bsomething\b",
        r"\bsomewhere\b",
        r"\banywhere\b",
        r"\bchill\b",
        r"\bquiet\b",
        r"\brelaxed\b",
        r"\bnice\b",
        r"\beasy\b",
    )
)

_LOCATION_VIBE_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "for",
        "to",
        "of",
        "in",
        "on",
        "at",
        "or",
        "and",
        "place",
        "spot",
        "area",
        "stop",
        "option",
        "please",
    }
)

# Leftover tokens that still count as location-only (not activity intent).
_LOCATION_NOUNS: frozenset[str] = frozenset(
    {
        "station",
        "hotel",
        "hostel",
        "metro",
        "subway",
        "airport",
        "lobby",
        "entrance",
        "exit",
        "terminal",
        "platform",
        "square",
        "plaza",
        "district",
        "neighborhood",
        "neighbourhood",
        "ward",
    }
)

# Proximity framing — with these, leftover named places (Shinjuku, Ueno, …) stay
# ambiguous unless a substantive activity token is also present.
_PROXIMITY_FRAME_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bnear(?:by)?\b",
        r"\bclose\s+to\b",
        r"\bclose\s*by\b",
        r"\bby\s+the\b",
        r"\baround(?:\s+the)?\b",
        r"\bwithin\s+walking\s+distance\b",
        r"\bsomewhere(?:\s+in)?\b",
        r"\banywhere(?:\s+in)?\b",
    )
)

# Activity / intent tokens that make a free-text hint non-food (not proximity-only).
_SUBSTANTIVE_ACTIVITY_TOKENS: frozenset[str] = frozenset(
    {
        "fun",
        "kids",
        "kid",
        "children",
        "child",
        "family",
        "families",
        "playground",
        "arcade",
        "amusement",
        "zoo",
        "aquarium",
        "activity",
        "activities",
        "explore",
        "sightseeing",
        "attraction",
        "attractions",
        "temple",
        "shrine",
        "hike",
        "hiking",
        "trail",
        "walk",
        "walking",
        "view",
        "views",
        "viewpoint",
        "photo",
        "photos",
        "instagram",
    }
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
    honor_food_hint: bool = False,
) -> bool:
    """Suggest-place should add a non-food stop when the day still lacks one.

    Only kicks in once the day already has 2+ stops (aligned with the hard
    day-balance gate at 3+ places). A single leftover food stop after delete
    must still allow dinner / another meal. A food-like one-off hint waives
    this balance nudge; any other one-off hint does not.
    """
    if honor_food_hint or food_crawl_mode:
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


def is_food_like_suggest_hint(hint: str) -> bool:
    """True when the one-off hint resolves to a food venue request.

    Food is judged only via food-category phrases (lunch, ramen, …). Words like
    kids/family alone are not food — but "food for kids" / "family dinner" are.
    """
    return infer_suggest_hint_category(hint) == "food"


def is_ambiguous_location_or_vibe_hint(hint: str) -> bool:
    """True for proximity/vibe-only hints that should not hard-ban food.

    Examples: "near the station", "near Shinjuku station", "somewhere in Ueno",
    "something chill nearby". Substantive free-text like "fun place for kids"
    is not ambiguous (even with a location suffix).
    """
    text = str(hint or "").strip()
    if not text:
        return False
    if infer_suggest_hint_category(text) is not None:
        return False
    has_proximity = any(pat.search(text) for pat in _PROXIMITY_FRAME_PATTERNS)
    cleaned = text
    for pat in _LOCATION_VIBE_FILLER_PATTERNS:
        cleaned = pat.sub(" ", cleaned)
    tokens = [
        tok
        for tok in re.findall(r"[A-Za-z0-9']+", cleaned.lower())
        if tok not in _LOCATION_VIBE_STOPWORDS and tok not in _LOCATION_NOUNS
    ]
    if has_proximity:
        # Named places may remain (Shinjuku, Ueno, Times…); only activity intent
        # makes the hint require non-food.
        return not any(tok in _SUBSTANTIVE_ACTIVITY_TOKENS for tok in tokens)
    # Pure vibe with no proximity frame: ambiguous only when nothing substantive
    # is left after stripping fillers.
    return not tokens


def hint_requires_non_food(hint: str) -> bool:
    """True when a non-empty hint must not resolve to category=food."""
    text = str(hint or "").strip()
    if not text:
        return False
    expected = infer_suggest_hint_category(text)
    if expected == "food":
        return False
    if expected is not None:
        return True
    return not is_ambiguous_location_or_vibe_hint(text)


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
    honor_food_hint: bool = False,
) -> None:
    """Reject another food stop when the day still has zero non-food."""
    if not prefer_non_food_suggestion(
        existing,
        food_crawl_mode=food_crawl_mode,
        honor_food_hint=honor_food_hint,
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
    """Reject places that conflict with the one-off hint.

    - Food-like hints require a food place.
    - Clear non-food category hints must match that category (and reject food).
    - Substantive free-text without a food phrase rejects food.
    - Proximity/vibe-only hints stay ambiguous (no hard food ban).
    """
    text = str(hint or "").strip()
    if not text:
        return
    expected = infer_suggest_hint_category(text)
    if expected == "food":
        if is_food_place(place):
            return
        raise ApiError(
            422,
            "suggestion did not match the user hint",
            code="hint_mismatch",
        )
    if hint_requires_non_food(text) and is_food_place(place):
        raise ApiError(
            422,
            "suggestion did not match the user hint",
            code="hint_mismatch",
        )
    if expected is None:
        return
    actual = str(place.get("category") or "").strip().lower()
    if actual == expected:
        return
    raise ApiError(
        422,
        "suggestion did not match the user hint",
        code="hint_mismatch",
    )
