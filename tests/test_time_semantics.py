from __future__ import annotations

import json
from pathlib import Path

import pytest

from rozkalns_weather.time_semantics import (
    CONTRACT_VERSION,
    DISPLAY_TIMEZONE,
    TimestampContractError,
    berlin_local_day_utc_bounds,
    berlin_local_month_utc_bounds,
    berlin_timestamp_view,
    validate_utc_timestamp,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads((ROOT / "tests/fixtures/timezone_dst_cases.json").read_text())
CONTRACT = json.loads((ROOT / "contracts/timezone-dst-v1.json").read_text())


def test_contract_registry_matches_source_constants() -> None:
    assert CONTRACT["contract_version"] == CONTRACT_VERSION
    assert CONTRACT["canonical_storage_timezone"] == "UTC"
    assert CONTRACT["display_timezone"] == DISPLAY_TIMEZONE
    assert CONTRACT["display_identity"]["repeated_autumn_hour_must_remain_distinct"] is True
    assert CONTRACT["reports"]["stored_forecast_and_observation_timestamps_remain_utc"] is True


def test_spring_forward_skips_nonexistent_berlin_hour() -> None:
    views = [berlin_timestamp_view(case["utc"]) for case in FIXTURES["spring_forward"]]
    assert [view["local_iso"] for view in views] == [case["local_iso"] for case in FIXTURES["spring_forward"]]
    assert [view["local_clock"] for view in views] == ["01:30:00", "03:30:00"]
    assert all(view["local_clock"] != "02:30:00" for view in views)


def test_autumn_repeated_hour_is_distinguished_by_offset_fold_and_utc() -> None:
    views = [berlin_timestamp_view(case["utc"]) for case in FIXTURES["autumn_repeat"]]
    assert [view["local_clock"] for view in views] == ["02:30:00", "02:30:00"]
    assert [view["utc_offset"] for view in views] == ["+02:00", "+01:00"]
    assert [view["fold"] for view in views] == [0, 1]
    assert views[0]["display_identity"] != views[1]["display_identity"]
    assert [view["local_iso"] for view in views] == [case["local_iso"] for case in FIXTURES["autumn_repeat"]]


def test_utc_date_and_berlin_calendar_grouping_remain_explicit() -> None:
    for case in FIXTURES["calendar_boundaries"]:
        view = berlin_timestamp_view(case["utc"])
        assert view["local_date"] == case["local_date"]
        assert view["local_month"] == case["local_month"]
        assert view["utc"] == case["utc"]


def test_machine_readable_timestamp_rejections_have_stable_reason_codes() -> None:
    for case in FIXTURES["invalid"]:
        evidence = validate_utc_timestamp(case["value"])
        assert evidence == {"state": "BLOCKED", "reason_code": case["reason_code"]}

    pass_evidence = validate_utc_timestamp("2026-10-25T01:30:00+00:00")
    assert pass_evidence == {
        "state": "PASS",
        "reason_code": "OK",
        "canonical_utc": "2026-10-25T01:30:00Z",
    }


def test_report_month_boundaries_follow_berlin_calendar_as_utc_half_open_intervals() -> None:
    for case in FIXTURES["report_periods"]:
        evidence = berlin_local_month_utc_bounds(case["month"])
        assert evidence["period_type"] == "berlin_local_month"
        assert evidence["timezone"] == DISPLAY_TIMEZONE
        assert evidence["start_utc"] == case["start_utc"]
        assert evidence["end_utc_exclusive"] == case["end_utc_exclusive"]
        assert evidence["duration_hours"] == case["duration_hours"]


def test_dst_transition_days_are_not_forced_to_twenty_four_hours() -> None:
    for case in FIXTURES["transition_days"]:
        evidence = berlin_local_day_utc_bounds(case["day"])
        assert evidence["duration_hours"] == case["duration_hours"]


def test_invalid_report_period_inputs_are_rejected_without_guessing() -> None:
    with pytest.raises(TimestampContractError) as month_error:
        berlin_local_month_utc_bounds("2026-13")
    assert month_error.value.reason_code == "INVALID_LOCAL_MONTH"

    with pytest.raises(TimestampContractError) as day_error:
        berlin_local_day_utc_bounds("2026-02-30")
    assert day_error.value.reason_code == "INVALID_LOCAL_DATE"
