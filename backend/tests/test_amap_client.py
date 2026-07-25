"""Amap client parsing unit tests."""

from __future__ import annotations

from places.amap_client import _amap_open_time_text, _parse_poi


def test_parse_poi_does_not_invent_operational() -> None:
    result = _parse_poi(
        {
            "id": "B000A7U3X0",
            "name": "豫园",
            "address": "福佑路",
            "cityname": "上海",
            "location": "121.492,31.227",
        }
    )
    assert result is not None
    assert result.place_id == "amap:B000A7U3X0"
    assert result.business_status is None
    assert result.provider == "amap"
    assert result.lat == 31.227
    assert result.lng == 121.492


def test_amap_open_time_from_biz_ext() -> None:
    text = _amap_open_time_text(
        {"biz_ext": {"open_time": "09:00-17:00"}}
    )
    assert text == "09:00-17:00"
