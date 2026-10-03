from datetime import timezone

import pytest

from rozkalns_weather.providers.provider_contracts import (
    BLOCKED,
    COMPATIBLE,
    WARN,
    ProviderContractDriftError,
    enforce_contract,
    inspect_open_meteo_metadata,
    inspect_open_meteo_single,
)


def test_open_meteo_single_contract_is_compatible() -> None:
    payload = {
        "hourly_units": {"time": "iso8601", "temperature_2m": "°C"},
        "hourly": {"time": ["2026-09-07T06:00"], "temperature_2m": [20.0]},
    }
    assert inspect_open_meteo_single(payload, requested_variables=("temperature_2m",)).status == COMPATIBLE


def test_missing_or_renamed_field_blocks() -> None:
    payload = {
        "hourly_units": {"time": "iso8601", "temperature": "°C"},
        "hourly": {"time": ["2026-09-07T06:00"], "temperature": [20.0]},
    }
    report = inspect_open_meteo_single(payload, requested_variables=("temperature_2m",))
    assert report.status == BLOCKED
    with pytest.raises(ProviderContractDriftError):
        enforce_contract(report)


def test_unit_drift_blocks() -> None:
    payload = {
        "hourly_units": {"time": "iso8601", "temperature_2m": "K"},
        "hourly": {"time": ["2026-09-07T06:00"], "temperature_2m": [293.15]},
    }
    report = inspect_open_meteo_single(payload, requested_variables=("temperature_2m",))
    assert report.status == BLOCKED
    assert report.reason_codes == ("UNIT_DRIFT",)


def test_run_metadata_must_be_valid() -> None:
    report = inspect_open_meteo_metadata({
        "last_run_initialisation_time": "invalid",
        "last_run_availability_time": 1788760800,
        "temporal_resolution_seconds": 3600,
        "update_interval_seconds": 10800,
    })
    assert report.status == BLOCKED
    assert "RUN_METADATA_INVALID" in report.reason_codes


def test_added_field_is_warning_not_silent_acceptance() -> None:
    payload = {
        "hourly_units": {"time": "iso8601", "temperature_2m": "°C", "new_upstream_field": "1"},
        "hourly": {"time": ["2026-09-07T06:00"], "temperature_2m": [20.0], "new_upstream_field": [1.0]},
    }
    report = inspect_open_meteo_single(payload, requested_variables=("temperature_2m",))
    assert report.status == WARN
    assert enforce_contract(report) == report
