from datetime import datetime, timezone
import io
import zipfile

import pytest

from rozkalns_weather.providers.provider_contracts import (
    BLOCKED,
    COMPATIBLE,
    WARN,
    ProviderContractDriftError,
    enforce_contract,
    inspect_dwd_mosmix_kmz,
    inspect_dwd_observations,
    inspect_open_meteo_ensemble,
    inspect_open_meteo_metadata,
    inspect_open_meteo_single,
)


def _kmz(*, temp_tokens: str = "293.15 294.15") -> bytes:
    kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"
 xmlns:dwd="https://opendata.dwd.de/weather/lib/pointforecast_dwd_extension_V1_0.xsd">
<Document>
<dwd:ProductDefinition><dwd:IssueTime>2026-09-07T00:00:00Z</dwd:IssueTime></dwd:ProductDefinition>
<dwd:ForecastTimeSteps>
<dwd:TimeStep>2026-09-07T01:00:00Z</dwd:TimeStep>
<dwd:TimeStep>2026-09-07T02:00:00Z</dwd:TimeStep>
</dwd:ForecastTimeSteps>
<Placemark><ExtendedData>
<dwd:Forecast dwd:elementName="TTT"><dwd:value>{temp_tokens}</dwd:value></dwd:Forecast>
</ExtendedData></Placemark>
</Document></kml>"""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("MOSMIX.kml", kml)
    return stream.getvalue()


def test_compatible_contracts_are_network_independent() -> None:
    observations = {
        "sources": [{"id": 7, "wmo_station_id": "10416"}],
        "weather": [{
            "timestamp": "2026-09-07T08:00:00+00:00",
            "source_id": 7,
            "temperature": 19.5,
        }],
    }
    single = {
        "hourly_units": {"time": "iso8601", "temperature_2m": "°C"},
        "hourly": {"time": ["2026-09-07T06:00"], "temperature_2m": [20.0]},
    }
    assert inspect_dwd_observations(observations, expected_wmo_station_id="10416").status == COMPATIBLE
    assert inspect_dwd_mosmix_kmz(_kmz(), expected_station_id="10416", station_id="10416").status == COMPATIBLE
    assert inspect_open_meteo_single(single, requested_variables=("temperature_2m",)).status == COMPATIBLE


def test_missing_or_renamed_open_meteo_field_blocks() -> None:
    payload = {
        "hourly_units": {"time": "iso8601", "temperature": "°C"},
        "hourly": {"time": ["2026-09-07T06:00"], "temperature": [20.0]},
    }
    report = inspect_open_meteo_single(payload, requested_variables=("temperature_2m",))
    assert report.status == BLOCKED
    assert "FIELD_MISSING" in report.reason_codes
    assert "FIELD_ADDED" in report.reason_codes


def test_open_meteo_unit_drift_blocks() -> None:
    payload = {
        "hourly_units": {"time": "iso8601", "temperature_2m": "K"},
        "hourly": {"time": ["2026-09-07T06:00"], "temperature_2m": [293.15]},
    }
    report = inspect_open_meteo_single(payload, requested_variables=("temperature_2m",))
    assert report.status == BLOCKED
    assert report.reason_codes == ("UNIT_DRIFT",)


def test_malformed_run_metadata_blocks() -> None:
    report = inspect_open_meteo_metadata({
        "last_run_initialisation_time": "invalid",
        "last_run_availability_time": 1788760800,
        "temporal_resolution_seconds": 3600,
        "update_interval_seconds": 10800,
    })
    assert report.status == BLOCKED
    assert "RUN_METADATA_INVALID" in report.reason_codes


def test_station_mismatch_blocks_without_discarding_report() -> None:
    payload = {
        "sources": [{"id": 7, "wmo_station_id": "99999"}],
        "weather": [{
            "timestamp": "2026-09-07T08:00:00+00:00",
            "source_id": 7,
            "temperature": 19.5,
        }],
    }
    report = inspect_dwd_observations(payload, expected_wmo_station_id="10416")
    assert report.status == BLOCKED
    assert "STATION_MISMATCH" in report.reason_codes
    with pytest.raises(ProviderContractDriftError) as exc:
        enforce_contract(report)
    assert exc.value.report == report


def test_ensemble_member_shape_change_blocks() -> None:
    payload = {
        "hourly_units": {
            "time": "iso8601",
            "temperature_2m": "°C",
            "temperature_2m_member01": "°C",
            "precipitation": "mm",
        },
        "hourly": {
            "time": ["2026-09-07T06:00"],
            "temperature_2m": [20.0],
            "temperature_2m_member01": [19.0],
            "precipitation": [0.0],
        },
    }
    report = inspect_open_meteo_ensemble(
        payload,
        requested_variables=("temperature_2m", "precipitation"),
    )
    assert report.status == BLOCKED
    assert "MEMBER_SHAPE_MISMATCH" in report.reason_codes


def test_mosmix_series_length_mismatch_uses_valid_kmz_fixture() -> None:
    report = inspect_dwd_mosmix_kmz(
        _kmz(temp_tokens="293.15"),
        expected_station_id="10416",
        station_id="10416",
    )
    assert report.status == BLOCKED
    assert report.reason_codes == ("SERIES_LENGTH_MISMATCH",)


def test_added_field_is_warning_not_silent_acceptance() -> None:
    payload = {
        "hourly_units": {
            "time": "iso8601",
            "temperature_2m": "°C",
            "new_upstream_field": "1",
        },
        "hourly": {
            "time": ["2026-09-07T06:00"],
            "temperature_2m": [20.0],
            "new_upstream_field": [1.0],
        },
    }
    report = inspect_open_meteo_single(payload, requested_variables=("temperature_2m",))
    assert report.status == WARN
    assert report.reason_codes == ("FIELD_ADDED",)
    assert enforce_contract(report) == report
