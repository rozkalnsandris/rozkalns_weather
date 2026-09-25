from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from rozkalns_weather.app import create_app
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database
from rozkalns_weather.models import ForecastRun, ForecastValue
from rozkalns_weather.providers.provider_contracts import BLOCKED, COMPATIBLE, inspect_open_meteo_single
from rozkalns_weather.semantics import SemanticGateError
from rozkalns_weather.weather_conditions import (
    CONDITION_CONTRACT_VERSION,
    FALLBACK_CONTRACT_VERSION,
    condition_from_wmo,
    daylight_state,
    fallback_condition,
    hourly_condition_rows,
)


@pytest.mark.parametrize(
    ("code", "condition"),
    [
        (0, "clear"),
        (1, "mostly_clear"),
        (2, "partly_cloudy"),
        (3, "overcast"),
        (45, "fog"),
        (48, "fog"),
        (51, "drizzle"),
        (55, "drizzle"),
        (56, "freezing_precipitation"),
        (67, "freezing_precipitation"),
        (61, "rain"),
        (65, "heavy_rain"),
        (71, "snow"),
        (77, "snow"),
        (80, "rain"),
        (82, "heavy_rain"),
        (85, "snow"),
        (95, "thunderstorm"),
        (97, "thunderstorm"),
        (96, "thunderstorm_hail"),
        (99, "thunderstorm_hail"),
    ],
)
def test_documented_wmo_families_map_without_mislabeling(code: int, condition: str) -> None:
    result = condition_from_wmo(code)
    assert result["condition"] == condition
    assert result["weather_code"] == code
    assert result["condition_source"] == "wmo_weather_code"


def test_fallback_thresholds_are_explicit_and_never_fabricate_adverse_phenomena() -> None:
    assert fallback_condition(precipitation_mm=0.0, cloud_cover_percent=19.9)["condition"] == "clear"
    assert fallback_condition(precipitation_mm=0.0, cloud_cover_percent=20.0)["condition"] == "mostly_clear"
    assert fallback_condition(precipitation_mm=0.0, cloud_cover_percent=45.0)["condition"] == "partly_cloudy"
    assert fallback_condition(precipitation_mm=0.0, cloud_cover_percent=80.0)["condition"] == "overcast"
    assert fallback_condition(precipitation_mm=0.05, cloud_cover_percent=100)["condition"] == "drizzle"
    assert fallback_condition(precipitation_mm=0.2, cloud_cover_percent=0)["condition"] == "rain"
    assert fallback_condition(precipitation_mm=2.0, cloud_cover_percent=0)["condition"] == "heavy_rain"
    unknown = fallback_condition(precipitation_mm=None, cloud_cover_percent=None)
    assert unknown["condition"] == "unknown"
    allowed = {"clear", "mostly_clear", "partly_cloudy", "overcast", "drizzle", "rain", "heavy_rain", "unknown"}
    for precip in (None, 0.0, 0.1, 0.5, 3.0):
        for cloud in (None, 0.0, 50.0, 100.0):
            assert fallback_condition(precipitation_mm=precip, cloud_cover_percent=cloud)["condition"] in allowed


def test_provider_daylight_wins_and_local_clock_is_last_resort() -> None:
    assert daylight_state(is_day=1, valid_time_utc="2026-12-01T23:00:00Z", timezone_name="Europe/Berlin") == {
        "daylight": "day",
        "daylight_source": "provider_is_day",
    }
    assert daylight_state(is_day=0, valid_time_utc="2026-06-01T10:00:00Z", timezone_name="Europe/Berlin") == {
        "daylight": "night",
        "daylight_source": "provider_is_day",
    }
    fallback = daylight_state(
        is_day=None,
        valid_time_utc="2026-09-25T10:00:00Z",
        timezone_name="Europe/Berlin",
    )
    assert fallback["daylight"] == "day"
    assert fallback["daylight_source"] == "timezone-hour-fallback-v1"


def test_semantic_gate_accepts_supported_codes_and_rejects_invalid_condition_values() -> None:
    ForecastValue(
        valid_time_utc=datetime(2026, 9, 25, 12, tzinfo=timezone.utc),
        lead_hours=1,
        variable="weather_code",
        value=99,
        unit="wmo_code",
    )
    ForecastValue(
        valid_time_utc=datetime(2026, 9, 25, 12, tzinfo=timezone.utc),
        lead_hours=1,
        variable="is_day",
        value=1,
        unit="1",
    )
    with pytest.raises(SemanticGateError, match="invalid_weather_code"):
        ForecastValue(
            valid_time_utc=datetime(2026, 9, 25, 12, tzinfo=timezone.utc),
            lead_hours=1,
            variable="weather_code",
            value=4,
            unit="wmo_code",
        )
    with pytest.raises(SemanticGateError, match="invalid_is_day"):
        ForecastValue(
            valid_time_utc=datetime(2026, 9, 25, 12, tzinfo=timezone.utc),
            lead_hours=1,
            variable="is_day",
            value=0.5,
            unit="1",
        )


def test_open_meteo_contract_requires_requested_condition_columns() -> None:
    payload = {
        "hourly_units": {"time": "iso8601", "weather_code": "wmo code", "is_day": ""},
        "hourly": {
            "time": ["2026-09-25T12:00"],
            "weather_code": [2],
            "is_day": [1],
        },
    }
    assert inspect_open_meteo_single(
        payload,
        requested_variables=("weather_code", "is_day"),
    ).status == COMPATIBLE

    missing = {
        "hourly_units": {"time": "iso8601", "weather_code": "wmo code"},
        "hourly": {"time": ["2026-09-25T12:00"], "weather_code": [2]},
    }
    report = inspect_open_meteo_single(
        missing,
        requested_variables=("weather_code", "is_day"),
    )
    assert report.status == BLOCKED
    assert "FIELD_MISSING" in report.reason_codes


def _value(valid: datetime, lead: float, variable: str, value: float, unit: str, window=None) -> ForecastValue:
    return ForecastValue(
        valid_time_utc=valid,
        lead_hours=lead,
        variable=variable,
        value=value,
        unit=unit,
        accumulation_window_minutes=window,
    )


def test_hourly_conditions_keep_provider_run_and_valid_time_aligned(tmp_path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'conditions.db'}")
    database.initialize()
    init = datetime(2026, 9, 25, 6, tzinfo=timezone.utc)
    valid = init + timedelta(hours=2)
    retrieved = init + timedelta(hours=1)
    for provider, model, code, is_day in (
        ("icon_d2", "ICON-D2", 2, 1),
        ("ecmwf_ifs", "IFS HRES", 95, 0),
    ):
        database.insert_forecast_run(
            ForecastRun(
                provider=provider,
                model_provider="fixture",
                model_name=model,
                init_time_utc=init,
                retrieved_at_utc=retrieved,
                source_surface="fixture",
                values=(
                    _value(valid, 2, "weather_code", code, "wmo_code"),
                    _value(valid, 2, "is_day", is_day, "1"),
                    _value(valid, 2, "cloud_cover", 60, "%"),
                    _value(valid, 2, "precipitation_1h", 1, "mm", 60),
                ),
            ),
            location_id="home",
        )

    rows = hourly_condition_rows(
        database,
        hours=48,
        timezone_name="Europe/Berlin",
        location_id="home",
    )
    assert {(row["provider"], row["condition"], row["daylight"]) for row in rows} == {
        ("icon_d2", "partly_cloudy", "day"),
        ("ecmwf_ifs", "thunderstorm", "night"),
    }
    assert all(row["contract"] == CONDITION_CONTRACT_VERSION for row in rows)
    assert all(row["provenance_alignment"] == "same_provider_latest_run_valid_time" for row in rows)


def test_daily_api_adds_deterministic_most_severe_condition_without_breaking_old_fields(tmp_path) -> None:
    settings = Settings.from_env(
        {
            "DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}",
            "HOME_LAT": "51.5",
            "HOME_LON": "7.6",
        }
    )
    database = Database(settings.database_url)
    client = TestClient(create_app(settings=settings, database=database))

    init = datetime(2026, 9, 25, 6, tzinfo=timezone.utc)
    retrieved = init + timedelta(minutes=45)
    first = init + timedelta(hours=1)
    second = init + timedelta(hours=2)
    database.insert_forecast_run(
        ForecastRun(
            provider="icon_d2",
            model_provider="DWD",
            model_name="ICON-D2",
            init_time_utc=init,
            retrieved_at_utc=retrieved,
            source_surface="fixture",
            values=(
                _value(first, 1, "temperature_2m", 15, "degC"),
                _value(second, 2, "temperature_2m", 17, "degC"),
                _value(first, 1, "precipitation_1h", 0, "mm", 60),
                _value(second, 2, "precipitation_1h", 4, "mm", 60),
                _value(first, 1, "cloud_cover", 30, "%"),
                _value(second, 2, "cloud_cover", 95, "%"),
                _value(first, 1, "weather_code", 2, "wmo_code"),
                _value(second, 2, "weather_code", 95, "wmo_code"),
                _value(first, 1, "is_day", 1, "1"),
                _value(second, 2, "is_day", 1, "1"),
            ),
        ),
        location_id="home",
    )

    response = client.get("/api/daily?days=2&location_id=home")
    assert response.status_code == 200
    row = response.json()["days_by_provider"][0]
    assert row["temperature_min_c"] == 15
    assert row["temperature_max_c"] == 17
    assert row["precipitation_total_mm"] == 4
    assert row["condition"] == "thunderstorm"
    assert row["condition_label"] == "Thunderstorm"
    assert row["weather_code"] == 95
    assert row["condition_source"] == "daily_most_severe_v1:wmo_weather_code"
    assert row["condition_daylight"] == "day"
    assert row["condition_evidence_count"] == 2


def test_existing_corpus_without_weather_code_or_is_day_uses_safe_daily_fallback(tmp_path) -> None:
    settings = Settings.from_env(
        {
            "DATABASE_URL": f"sqlite:///{tmp_path / 'legacy.db'}",
            "HOME_LAT": "51.5",
            "HOME_LON": "7.6",
        }
    )
    database = Database(settings.database_url)
    client = TestClient(create_app(settings=settings, database=database))

    init = datetime(2026, 9, 25, 6, tzinfo=timezone.utc)
    valid = init + timedelta(hours=1)
    database.insert_forecast_run(
        ForecastRun(
            provider="icon_d2",
            model_provider="DWD",
            model_name="ICON-D2",
            init_time_utc=init,
            retrieved_at_utc=init + timedelta(minutes=30),
            source_surface="legacy-fixture",
            values=(
                _value(valid, 1, "temperature_2m", 16, "degC"),
                _value(valid, 1, "precipitation_1h", 0, "mm", 60),
                _value(valid, 1, "cloud_cover", 10, "%"),
            ),
        ),
        location_id="home",
    )
    row = client.get("/api/daily?days=1&location_id=home").json()["days_by_provider"][0]
    assert row["condition"] == "clear"
    assert row["weather_code"] is None
    assert row["condition_source"] == f"daily_most_severe_v1:{FALLBACK_CONTRACT_VERSION}"
