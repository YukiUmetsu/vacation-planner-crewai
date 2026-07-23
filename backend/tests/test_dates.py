from services.dates import inclusive_day_count, validate_trip_dates
from http_utils import ApiError
import pytest
from datetime import date


def test_inclusive_day_count() -> None:
    assert inclusive_day_count(date(2026, 9, 1), date(2026, 9, 1)) == 1
    assert inclusive_day_count(date(2026, 9, 1), date(2026, 9, 7)) == 7


def test_validate_trip_dates_ok() -> None:
    start, end, count = validate_trip_dates("2026-09-01", "2026-09-07")
    assert count == 7
    assert start.isoformat() == "2026-09-01"


def test_validate_trip_dates_rejects_too_long() -> None:
    with pytest.raises(ApiError) as exc:
        validate_trip_dates("2026-09-01", "2026-09-20")
    assert exc.value.status_code == 400
    assert exc.value.code == "trip_too_long"


def test_validate_trip_dates_rejects_fifteen_inclusive_days() -> None:
    # Aug 1–15 is end−start=14 but inclusive count is 15.
    with pytest.raises(ApiError) as exc:
        validate_trip_dates("2026-08-01", "2026-08-15")
    assert exc.value.status_code == 400
    assert exc.value.code == "trip_too_long"
    assert "inclusive" in exc.value.message


def test_validate_trip_dates_allows_fourteen_inclusive_days() -> None:
    _, _, count = validate_trip_dates("2026-08-01", "2026-08-14")
    assert count == 14


def test_validate_trip_dates_rejects_inverted() -> None:
    with pytest.raises(ApiError) as exc:
        validate_trip_dates("2026-09-10", "2026-09-01")
    assert exc.value.status_code == 400
