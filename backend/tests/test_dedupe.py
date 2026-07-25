from planning_quality.dedupe import (
    dedupe_places,
    ensure_place_key,
    place_identity_tokens,
)


def test_ensure_place_key_fills_missing() -> None:
    key = ensure_place_key({"name": "Louvre", "address": "Paris"})
    assert key == "louvre|paris"


def test_ensure_place_key_rewrites_bare_slug() -> None:
    key = ensure_place_key(
        {"name": "Nijo Castle", "address": "Kyoto", "place_key": "nijo_castle"}
    )
    assert key == "nijo castle|kyoto"


def test_dedupe_drops_visited() -> None:
    places = [
        {"name": "A", "address": "1", "place_key": "a|1"},
        {"name": "B", "address": "2", "place_key": "b|2"},
    ]
    out = dedupe_places(places, ["a|1"])
    assert len(out) == 1
    assert out[0]["place_key"] == "b|2"


def test_dedupe_fills_keys() -> None:
    places = [{"name": "Cafe", "address": "Tokyo"}]
    out = dedupe_places(places, [])
    assert out[0]["place_key"] == "cafe|tokyo"


def test_dedupe_drops_same_name_different_keys() -> None:
    places = [
        {"name": "Nijo Castle", "address": "Kyoto", "place_key": "nijo_castle"},
        {
            "name": "Nijo Castle",
            "address": "Nakagyo Ward, Kyoto",
            "place_key": "nijo castle|nakagyo ward, kyoto",
        },
    ]
    out = dedupe_places(places, [])
    assert len(out) == 1
    assert out[0]["place_key"] == "nijo castle|kyoto"


def test_dedupe_drops_visited_by_name_part() -> None:
    places = [
        {
            "name": "Nijo Castle",
            "address": "Kyoto",
            "place_key": "nijocastle",
        }
    ]
    out = dedupe_places(places, ["nijo castle|kyoto station area"])
    assert out == []


def test_dedupe_drops_compact_slug_visited() -> None:
    places = [
        {
            "name": "Nijo Castle",
            "address": "Nakagyo, Kyoto",
            "place_key": "nijo castle|nakagyo, kyoto",
        }
    ]
    out = dedupe_places(places, ["nijocastle"])
    assert out == []


def test_dedupe_drops_same_google_place_id() -> None:
    places = [
        {
            "name": "Cafe A",
            "address": "1 St",
            "place_key": "cafe a|1 st",
            "place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
        },
        {
            "name": "Cafe A Branch Label",
            "address": "2 St",
            "place_key": "cafe a branch label|2 st",
            "place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
        },
    ]
    out = dedupe_places(places, [])
    assert len(out) == 1
    assert "id:ChIJN1t_tDeuEmsRUsoyG83frY4" in place_identity_tokens(out[0])
