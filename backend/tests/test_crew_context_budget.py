"""Tests for crew input char-budget slimming."""

from __future__ import annotations

import json

from services.crew_context_budget import inputs_char_len, slim_crew_inputs


def _base_day_inputs(**overrides: object) -> dict:
    data: dict = {
        "origin": "NYC",
        "destination": "Japan",
        "destination_type": "country",
        "day_index": "5",
        "date": "2026-09-05",
        "overnight_city": "Tokyo",
        "preferences": "food",
        "energy_level": "3",
        "max_comfortable_minutes": "510",
        "interests": "temples",
        "already_visited": "",
        "prior_days_summary": "",
        "city_route_json": "",
    }
    data.update(overrides)
    return data


def test_under_budget_is_noop() -> None:
    inputs = _base_day_inputs(
        already_visited="sensoji|tokyo,meiji|tokyo",
        prior_days_summary="Day 1: temples @ Tokyo",
    )
    slimmed = slim_crew_inputs(
        inputs,
        overnight_city="Tokyo",
        day_index=5,
        max_chars=50_000,
        already_visited_repeats=3,
    )
    assert slimmed == inputs


def test_slims_already_visited_first_prefers_same_city_and_recent() -> None:
    # Older Kyoto keys + recent Tokyo keys — under a tight budget prefer Tokyo, then recent.
    older = [f"old{i}|kyoto" for i in range(40)]
    recent = [f"spot{i}|tokyo" for i in range(10)]
    visited = ",".join(older + recent)
    inputs = _base_day_inputs(already_visited=visited)
    full_len = inputs_char_len(inputs, already_visited_repeats=3)
    assert full_len > 900

    slimmed = slim_crew_inputs(
        inputs,
        overnight_city="Tokyo",
        day_index=5,
        max_chars=900,
        already_visited_repeats=3,
    )
    kept = [k for k in slimmed["already_visited"].split(",") if k]
    assert 0 < len(kept) < 50
    assert set(recent).issubset(set(kept))
    kyoto_kept = [k for k in kept if k.endswith("|kyoto")]
    assert kyoto_kept == older[-len(kyoto_kept) :]
    assert inputs_char_len(slimmed, already_visited_repeats=3) <= 900
    # Full list unchanged in original
    assert inputs["already_visited"] == visited


def test_slims_prior_days_when_still_over_after_visited() -> None:
    # Empty visited so step 1 cannot absorb the overflow; prior lines must shrink.
    lines = [f"Day {i}: theme @ City{i} with extra detail" for i in range(1, 50)]
    inputs = _base_day_inputs(
        already_visited="",
        prior_days_summary="\n".join(lines),
    )
    full_len = inputs_char_len(inputs, already_visited_repeats=3)
    budget = min(900, full_len - 100)
    assert budget < full_len

    slimmed = slim_crew_inputs(
        inputs,
        overnight_city="Tokyo",
        day_index=5,
        max_chars=budget,
        already_visited_repeats=3,
    )
    prior_lines = [
        line for line in str(slimmed["prior_days_summary"]).splitlines() if line
    ]
    assert len(prior_lines) < len(lines)
    if prior_lines:
        assert "\n".join(prior_lines) == "\n".join(lines[-len(prior_lines) :])
    assert inputs_char_len(slimmed, already_visited_repeats=3) <= budget


def test_does_not_touch_prior_when_visited_slim_is_enough() -> None:
    older = [f"old{i}|kyoto" for i in range(40)]
    recent = [f"spot{i}|tokyo" for i in range(10)]
    prior = "Day 1: hello @ Tokyo\nDay 2: food @ Tokyo"
    inputs = _base_day_inputs(
        already_visited=",".join(older + recent),
        prior_days_summary=prior,
    )
    slimmed = slim_crew_inputs(
        inputs,
        overnight_city="Tokyo",
        day_index=5,
        max_chars=1_200,
        already_visited_repeats=3,
    )
    assert slimmed["prior_days_summary"] == prior
    assert len(slimmed["already_visited"]) < len(inputs["already_visited"])
    assert inputs_char_len(slimmed, already_visited_repeats=3) <= 1_200


def test_slims_city_route_to_overnight_window() -> None:
    route = {
        "cities": [
            {
                "city": "Osaka",
                "arrival_day_index": 1,
                "departure_day_index": 3,
                "nights": 2,
                "summary": "x" * 500,
            },
            {
                "city": "Tokyo",
                "arrival_day_index": 4,
                "departure_day_index": 7,
                "nights": 3,
                "summary": "y" * 500,
            },
            {
                "city": "Kyoto",
                "arrival_day_index": 8,
                "departure_day_index": 10,
                "nights": 2,
                "summary": "z" * 500,
            },
        ],
        "total_nights": 7,
        "overview": "long " * 200,
    }
    # Large prefs + route push over budget once visited is empty.
    inputs = _base_day_inputs(
        already_visited="",
        prior_days_summary="",
        city_route_json=json.dumps(route),
        preferences="p" * 800,
    )
    slimmed = slim_crew_inputs(
        inputs,
        overnight_city="Tokyo",
        day_index=5,
        max_chars=1_200,
        already_visited_repeats=1,
    )
    route_raw = str(slimmed["city_route_json"] or "")
    if route_raw:
        parsed = json.loads(route_raw)
        cities = [c.get("city") for c in parsed.get("cities") or []]
        assert "Tokyo" in cities
        assert "Kyoto" not in cities or len(cities) == 1
    assert inputs_char_len(slimmed, already_visited_repeats=1) <= 1_200


def test_slims_preferences_last() -> None:
    inputs = _base_day_inputs(
        already_visited="",
        prior_days_summary="",
        city_route_json="",
        preferences="want " + ("museums and food " * 200),
    )
    slimmed = slim_crew_inputs(
        inputs,
        overnight_city="Tokyo",
        day_index=5,
        max_chars=400,
        already_visited_repeats=1,
    )
    assert len(slimmed["preferences"]) < len(str(inputs["preferences"]))
    assert inputs_char_len(slimmed, already_visited_repeats=1) <= 400


def test_effective_len_accounts_for_repeats() -> None:
    inputs = _base_day_inputs(already_visited="a" * 100)
    base = inputs_char_len(inputs, already_visited_repeats=1)
    triple = inputs_char_len(inputs, already_visited_repeats=3)
    assert triple == base + 200
