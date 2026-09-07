from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from rozkalns_weather.db import Database
from rozkalns_weather.locations import DWD_10416
from rozkalns_weather.models import ForecastRun, ForecastValue, Observation
from rozkalns_weather.reporting import monthly_weather_next_report


def _database(tmp_path: Path) -> Database:
    database = Database(f"sqlite:///{tmp_path / 'reporting.db'}")
    database.initialize()
    database.ensure_location(
        location_id=DWD_10416.id,
        label=DWD_10416.label,
        lat=DWD_10416.lat,
        lon=DWD_10416.lon,
        elevation_m=DWD_10416.elevation_m,
        timezone=DWD_10416.timezone,
    )
    return database


def test_monthly_v3_has_common_ci_wins_ensemble_calibration_and_events(tmp_path: Path) -> None:
    database = _database(tmp_path)
    start = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
    observations: list[Observation] = []

    for index in range(30):
        valid = start + timedelta(hours=index)
        observed_temperature = 10.0 + index / 10
        observations.append(
            Observation(
                source_provider="DWD",
                station_id="10416",
                location_id=DWD_10416.id,
                observed_at_utc=valid,
                variable="temperature_2m",
                value=observed_temperature,
                unit="degC",
            )
        )
        if index < 2:
            observations.extend(
                [
                    Observation(
                        source_provider="DWD",
                        station_id="10416",
                        location_id=DWD_10416.id,
                        observed_at_utc=valid,
                        variable="precipitation_1h",
                        value=0.2 if index == 0 else 0.0,
                        unit="mm",
                    ),
                    Observation(
                        source_provider="DWD",
                        station_id="10416",
                        location_id=DWD_10416.id,
                        observed_at_utc=valid,
                        variable="wind_gust_10m",
                        value=16.0 if index == 0 else 8.0,
                        unit="m/s",
                    ),
                ]
            )

        init = valid - timedelta(hours=6)
        for provider, model_provider, model_name, model_version, error in (
            ("weathernext3", "Google DeepMind", "WeatherNext 3", "3.0.0", 1.0),
            ("icon_d2", "DWD", "ICON-D2", None, 2.0),
        ):
            values = [
                ForecastValue(
                    valid_time_utc=valid,
                    lead_hours=6,
                    variable="temperature_2m",
                    statistic="mean" if provider == "weathernext3" else "deterministic",
                    value=observed_temperature + error,
                    unit="degC",
                )
            ]
            if provider == "icon_d2" and index < 2:
                values.extend(
                    [
                        ForecastValue(
                            valid_time_utc=valid,
                            lead_hours=6,
                            variable="precipitation_1h",
                            statistic="deterministic",
                            value=0.3 if index == 0 else 0.0,
                            unit="mm",
                            accumulation_window_minutes=60,
                        ),
                        ForecastValue(
                            valid_time_utc=valid,
                            lead_hours=6,
                            variable="wind_gust_10m",
                            statistic="deterministic",
                            value=17.0 if index == 0 else 7.0,
                            unit="m/s",
                        ),
                    ]
                )
            database.insert_forecast_run(
                ForecastRun(
                    provider=provider,
                    model_provider=model_provider,
                    model_name=model_name,
                    model_version=model_version,
                    init_time_utc=init,
                    retrieved_at_utc=init + timedelta(hours=1),
                    source_surface="fixture",
                    values=tuple(values),
                ),
                location_id=DWD_10416.id,
            )

    database.insert_observations(observations)

    ensemble_values: list[ForecastValue] = []
    for index in range(2):
        valid = start + timedelta(hours=index)
        observed_temperature = 10.0 + index / 10
        for member_id, temperature, precipitation in (
            ("member_00", observed_temperature - 0.5, 0.0),
            ("member_01", observed_temperature + 0.5, 0.3),
        ):
            ensemble_values.extend(
                [
                    ForecastValue(
                        valid_time_utc=valid,
                        lead_hours=12 + index,
                        variable="temperature_2m",
                        statistic=member_id,
                        value=temperature,
                        unit="degC",
                    ),
                    ForecastValue(
                        valid_time_utc=valid,
                        lead_hours=12 + index,
                        variable="precipitation_1h",
                        statistic=member_id,
                        value=precipitation,
                        unit="mm",
                        accumulation_window_minutes=60,
                    ),
                ]
            )
    database.insert_forecast_run(
        ForecastRun(
            provider="icon_d2_eps",
            model_provider="DWD",
            model_name="ICON-D2-EPS",
            init_time_utc=start - timedelta(hours=12),
            retrieved_at_utc=start - timedelta(hours=1),
            source_surface="fixture ensemble members",
            transport_provider="Open-Meteo",
            init_time_quality="fixture_only",
            values=tuple(ensemble_values),
        ),
        location_id=DWD_10416.id,
    )

    report = monthly_weather_next_report(database, month="2026-09")
    assert report["report_type"] == "station_benchmark_monthly_v3"

    weather_next = next(
        row
        for row in report["common_sample_leaderboard"]
        if row["provider"] == "weathernext3" and row["lead_bucket"] == "6-12h"
    )
    assert weather_next["n"] == 30
    assert weather_next["mae_bootstrap_95_ci"] is not None

    wins = next(
        row
        for row in report["common_sample_wins_losses"]
        if row["provider"] == "weathernext3" and row["lead_bucket"] == "6-12h"
    )
    assert wins["wins"] == 30
    assert wins["losses"] == 0

    ensemble = report["ensemble_calibration"]["icon_d2_eps"]
    assert ensemble["temperature_80_interval"]["n"] == 2
    assert ensemble["precipitation_probability"]["n"] == 2
    assert ensemble["precipitation_probability"]["brier_score"] is not None

    event_variables = {row["variable"] for row in report["event_summaries"]}
    assert {"temperature_2m", "precipitation_1h", "wind_gust_10m"} <= event_variables
