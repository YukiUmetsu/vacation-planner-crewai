from services.dedupe import dedupe_places, ensure_place_key


def test_ensure_place_key_fills_missing() -> None:
    key = ensure_place_key({"name": "Louvre", "address": "Paris"})
    assert key == "louvre|paris"


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
