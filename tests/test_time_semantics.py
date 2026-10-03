import pytest

from rozkalns_weather.time_semantics import (
    TimestampContractError,
    berlin_local_day_utc_bounds,
    berlin_local_month_utc_bounds,
    berlin_timestamp_view,
    validate_utc_timestamp,
)


def test_spring_forward_skips_nonexistent_hour() -> None:
    before = berlin_timestamp_view("2026-03-29T00:30:00Z")
    after = berlin_timestamp_view("2026-03-29T01:30:00Z")
    assert before["local_clock"] == "01:30:00"
    assert after["local_clock"] == "03:30:00"


def test_autumn_repeated_hour_keeps_distinct_offsets() -> None:
    first = berlin_timestamp_view("2026-10-25T00:30:00Z")
    second = berlin_timestamp_view("2026-10-25T01:30:00Z")
    assert first["local_clock"] == second["local_clock"] == "02:30:00"
    assert first["utc_offset"] != second["utc_offset"]
    assert first["display_identity"] != second["display_identity"]


def test_utc_validation_is_explicit() -> None:
    assert validate_utc_timestamp("2026-10-25T01:30:00+00:00")["state"] == "PASS"
    assert validate_utc_timestamp("2026-10-25T01:30:00")["state"] == "BLOCKED"


def test_berlin_month_and_transition_day_bounds() -> None:
    october = berlin_local_month_utc_bounds("2026-10")
    assert october["duration_hours"] == 745.0
    transition = berlin_local_day_utc_bounds("2026-10-25")
    assert transition["duration_hours"] == 25.0


def test_invalid_calendar_input_is_rejected() -> None:
    with pytest.raises(TimestampContractError):
        berlin_local_month_utc_bounds("2026-13")
