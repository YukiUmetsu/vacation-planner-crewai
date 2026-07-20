"""Trip date helpers (inclusive day windows, max 14)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from http_utils import ApiError

MAX_DAY_COUNT = 14


def parse_iso_date(value: str, *, field: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ApiError(400, f"{field} must be YYYY-MM-DD") from exc


def inclusive_day_count(start: date, end: date) -> int:
    return (end - start).days + 1


def validate_trip_dates(start_date: str, end_date: str) -> tuple[date, date, int]:
    start = parse_iso_date(start_date, field="start_date")
    end = parse_iso_date(end_date, field="end_date")
    if end < start:
        raise ApiError(400, "end_date must be on or after start_date")
    day_count = inclusive_day_count(start, end)
    if day_count < 1 or day_count > MAX_DAY_COUNT:
        raise ApiError(400, f"trip length must be 1..{MAX_DAY_COUNT} days (got {day_count})")
    return start, end, day_count


def date_for_day_index(start: date, day_index: int) -> date:
    return start + timedelta(days=day_index - 1)
