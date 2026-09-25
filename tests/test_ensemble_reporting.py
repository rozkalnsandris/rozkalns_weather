from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from rozkalns_weather.db import Database
from rozkalns_weather.locations import DWD_10416
from rozkalns_weather.models import ForecastRun, ForecastValue, Observation
from rozkalns_weather.reporting import monthly_weather_next_report


def test_complete_icon_d2_eps_member_set_is_admitted_to_probabilistic_metrics(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'ensemble-reporting.db'}")
    database.initialize()
    database.ensure_location(
        location_id=DWD_10416.id,
        label=DWD_10416.label,
        lat=DWD_10416.lat,
        lon=DWD_10416.lon,
        elevation_m=DWD_10416.elevation_m,
        timezone=DWD_10416.timezone,
    )

    valid = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
    database.insert_observations(
        [
            Observation(
                source_provider="DWD",
                station_id="10416",
                location_id=DWD_10416.id,
                observed_at_utc=valid,
                variable="temperature_2m",
                value=10.0,
                unit="degC",
            ),
            Observation(
                source_provider="DWD",
                station_id="10416",
                location_id=DWD_10416.id,
                observed_at_utc=valid,
                variable="precipitation_1h",
                value=0.2,
                unit="mm",
            ),
        ]
    )

    values: list[ForecastValue] = []
    for index in range(20):
        member_id = f"member_{index:02d}"
        values.extend(
            [
                ForecastValue(
                    valid_time_utc=valid,
                    lead_hours=12,
                    variable="temperature_2m",
                    statistic=member_id,
                    value=9.5 + index / 20,
                    unit="degC",
                ),
                ForecastValue(
                    valid_time_utc=valid,
                    lead_hours=12,
                    variable="precipitation_1h",
                    statistic=member_id,
                    value=0.0 if index < 10 else 0.3,
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
            model_version="fixture-v1",
            init_time_utc=datetime(2026, 9, 25, 0, tzinfo=timezone.utc),
            retrieved_at_utc=datetime(2026, 9, 25, 1, tzinfo=timezone.utc),
            source_surface="fixture ensemble members",
            transport_provider="Open-Meteo",
            source_metadata={"documented_member_count": 20},
            values=tuple(values),
        ),
        location_id=DWD_10416.id,
    )

    report = monthly_weather_next_report(database, month="2026-09")
    ensemble = report["ensemble_calibration"]["icon_d2_eps"]

    assert ensemble["n_member_groups"] == 2
    assert ensemble["n_metric_eligible_member_groups"] == 2
    assert ensemble["n_metric_excluded_member_groups"] == 0
    assert ensemble["member_completeness_status_counts"] == {"complete": 2}
    assert ensemble["member_exclusion_reason_counts"] == {"COMPLETE_MEMBER_SET": 2}
    assert ensemble["temperature_80_interval"]["n"] == 1
    assert ensemble["temperature_80_interval"]["mean_wis"] is not None
    assert ensemble["precipitation_probability"]["n"] == 1
    assert ensemble["precipitation_probability"]["brier_score"] is not None
    assert ensemble["precipitation_probability"]["reliability_bins"]
    assert ensemble["mean_crps_by_variable"].keys() == {
        "precipitation_1h",
        "temperature_2m",
    }
    assert all(
        item["status"] == "complete"
        and item["run_stability_status"] == "stable"
        and item["declared_member_count"] == 20
        for item in ensemble["member_completeness_evidence"]
    )
