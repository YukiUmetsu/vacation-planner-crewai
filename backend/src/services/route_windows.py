"""Normalize / validate CityRoute day windows and trip pacing."""

from __future__ import annotations

from typing import Any

from http_utils import ApiError


def max_cities_for_trip(*, day_count: int) -> int:
    """
    Cap overnight cities so short trips stay sane.

    total_nights = day_count - 1. Examples (max trip is 14 days → 13 nights):
    - 1–3 nights → 1 city
    - 4 nights → 2 cities
    - 5–8 nights → 3 cities  (6 nights Japan ≠ 5 cities)
    - 9–13 nights → 4 cities
    - 14+ nights → 5 cities (unreachable at current max trip length)
    """
    nights = max(0, int(day_count) - 1)
    if nights <= 3:
        return 1
    if nights <= 4:
        return 2
    if nights <= 8:
        return 3
    if nights <= 13:
        return 4
    return 5


def _largest_remainder_partition(total: int, weights: list[int]) -> list[int]:
    """
    Split ``total`` into len(weights) positive ints that sum exactly to ``total``.

    Used to turn city night-weights into contiguous day spans (e.g. 7 trip days
    and weights [3, 5] → [3, 4]) so every day is covered once and no city gets
    zero days.

    Algorithm (largest-remainder / Hamilton method):
    1. Give each slot the floored proportional share ``floor(total * w / sum(w))``.
    2. Ensure each share is at least 1 (trim the largest if that overshoots).
    3. Distribute leftover days one-by-one to the slots with the largest
       fractional remainders from step 1.
    """
    n = len(weights)
    if n == 0:
        return []
    if total < n:
        raise ApiError(
            400,
            f"cannot fit {n} cities into {total} days",
            code="route_too_many_cities",
        )
    positive = [max(1, int(w)) for w in weights]
    wsum = sum(positive)
    exact = [total * w / wsum for w in positive]
    floors = [int(x) for x in exact]
    for i in range(n):
        if floors[i] < 1:
            floors[i] = 1
    while sum(floors) > total:
        idx = max(range(n), key=lambda i: floors[i])
        if floors[idx] <= 1:
            break
        floors[idx] -= 1
    rem = total - sum(floors)
    order = sorted(
        range(n),
        key=lambda i: (exact[i] - int(exact[i]), positive[i]),
        reverse=True,
    )
    for i in order:
        if rem <= 0:
            break
        floors[i] += 1
        rem -= 1
    return floors


def _scale_nights(nights: list[int], expected: int) -> list[int]:
    n = len(nights)
    if n == 0:
        return []
    if expected < 0:
        expected = 0
    raw = sum(max(0, x) for x in nights)
    if raw <= 0:
        base, rem = divmod(expected, n)
        return [base + (1 if i < rem else 0) for i in range(n)]
    if raw == expected:
        return [max(0, int(x)) for x in nights]
    exact = [expected * max(0, int(x)) / raw for x in nights]
    scaled = [int(x) for x in exact]
    rem = expected - sum(scaled)
    order = sorted(
        range(n),
        key=lambda i: (exact[i] - int(exact[i]), nights[i]),
        reverse=True,
    )
    step = 1 if rem > 0 else -1
    for j in range(abs(rem)):
        idx = order[j % n]
        scaled[idx] = max(0, scaled[idx] + step)
    scaled[-1] = max(0, expected - sum(scaled[:-1]))
    return scaled


def _merge_stop_into(keeper: dict[str, Any], absorbed: dict[str, Any]) -> dict[str, Any]:
    out = dict(keeper)
    out["nights"] = int(keeper.get("nights") or 0) + int(absorbed.get("nights") or 0)
    absorbed_city = str(absorbed.get("city") or "").strip()
    if absorbed_city:
        reason = str(keeper.get("reason") or "").strip()
        note = f"Also covers {absorbed_city}"
        out["reason"] = f"{reason}; {note}" if reason else note
    highlights: list[Any] = []
    for src in (keeper, absorbed):
        for h in src.get("highlights") or []:
            if h not in highlights:
                highlights.append(h)
    out["highlights"] = highlights[:8]
    return out


def consolidate_route_cities(
    route: dict[str, Any],
    *,
    day_count: int,
) -> dict[str, Any]:
    """Drop excess cities by merging the lightest stops into neighbors."""
    cities = [dict(c) for c in (route.get("cities") or [])]
    if not cities:
        return route

    limit = max_cities_for_trip(day_count=day_count)
    while len(cities) > limit:
        # Prefer merging the smallest overnight stop into its previous neighbor.
        nights = [int(c.get("nights") or 0) for c in cities]
        # Skip index 0 when possible so we merge forward into an established base.
        candidates = list(range(1, len(cities))) or [0]
        merge_idx = min(candidates, key=lambda i: (nights[i], i))
        if merge_idx == 0:
            cities[1] = _merge_stop_into(cities[1], cities[0])
            del cities[0]
        else:
            cities[merge_idx - 1] = _merge_stop_into(
                cities[merge_idx - 1], cities[merge_idx]
            )
            del cities[merge_idx]

    return {**route, "cities": cities}


def normalize_route_windows(route: dict[str, Any], day_count: int) -> dict[str, Any]:
    """
    Pace-check and rebuild day windows for **crew proposals** only.

    Used by ``propose_cities`` before persist. User ``confirm_cities`` payloads
    are validated as-is (no silent rewrite).
    """
    day_count = int(day_count)
    paced = consolidate_route_cities(route, day_count=day_count)
    cities_in = list(paced.get("cities") or [])
    if not cities_in:
        return paced

    expected_nights = max(0, day_count - 1)
    nights = _scale_nights(
        [int(c.get("nights") or 0) for c in cities_in],
        expected_nights,
    )
    weights = [n + 1 for n in nights]
    spans = _largest_remainder_partition(day_count, weights)

    out_cities: list[dict[str, Any]] = []
    day = 1
    for stop, span, night in zip(cities_in, spans, nights, strict=True):
        item = dict(stop)
        item["nights"] = int(night)
        item["arrival_day_index"] = day
        item["departure_day_index"] = day + int(span) - 1
        out_cities.append(item)
        day += int(span)

    return {
        **paced,
        "cities": out_cities,
        "total_nights": expected_nights,
    }
