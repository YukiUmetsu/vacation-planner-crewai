"""Mainland China detector unit tests."""

from __future__ import annotations

from places.region import is_mainland_china


def test_mainland_china_cities() -> None:
    assert is_mainland_china("Shanghai")
    assert is_mainland_china("Beijing", "China")
    assert is_mainland_china("中国")


def test_not_mainland_sar_taiwan() -> None:
    assert not is_mainland_china("Hong Kong")
    assert not is_mainland_china("Hong Kong, China")
    assert not is_mainland_china("Macau")
    assert not is_mainland_china("Taiwan")


def test_non_china() -> None:
    assert not is_mainland_china("Tokyo")
    assert not is_mainland_china("Japan")
    assert not is_mainland_china("")
