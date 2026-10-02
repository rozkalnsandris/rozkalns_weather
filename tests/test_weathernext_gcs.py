from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from rozkalns_weather.locations import BENCHMARK_LOCATION
from rozkalns_weather.providers.weathernext import STATION_FIELDS, STATS, SURFACE_FIELDS
from rozkalns_weather.weathernext_gcs import (
    GCS_FULL_ENSEMBLE_BUCKET,
    GCS_STATISTICS_BUCKET,
    STATION_STATISTIC_VARIABLES,
    SURFACE_STATISTIC_VARIABLES,
    build_statistics_selection_plan,
    statistics_point_records_to_run,
    statistics_run_prefix,
    validate_statistics_schema,
)


def _schema_fixture() -> dict:
    return json.loads(
        Path("tests/fixtures/weathernext_gcs_statistics_schema.json").read_text()
    )


def _stat_values(base: float) -> dict[str, float]:
    offsets = {
        "mean": 0.0,
        "p10": -2.0,
        "p25": -1.0,
        "p50": 0.0,
        "p75": 1.0,
        "p90": 2.0,
    }
    return {stat: base + offsets[stat] for stat in STATS}


def _record(fields: dict, *, lead_hour: int) -> dict[str, float | int]:
    record: dict[str, float | int] = {"lead_hour": lead_hour}
    for index, field in enumerate(fields):
        if field == "total_precipitation_1hr":
            values = {
                "mean": 0.0010,
                "p10": 0.0001,
                "p25": 0.0004,
                "p50": 0.0008,
                "p75": 0.0014,
                "p90": 0.0020,
            }
        elif field == "total_cloud_cover":
            values = {
                "mean": 0.50,
                "p10": 0.10,
                "p25": 0.25,
                "p50": 0.50,
                "p75": 0.75,
                "p90": 0.90,
            }
        else:
            values = _stat_values(280.0 + index * 5.0)
        for stat, value in values.items():
            record[f"{field}_{stat}"] = value
    return record


def test_documented_statistics_run_path_requires_explicit_matching_token() -> None:
    init = datetime(2026, 8, 26, 0, tzinfo=timezone.utc)
    prefix = statistics_run_prefix(
        init_time=init,
        run_directory="20260826_00hr_01_preds",
    )
    assert prefix == (
        "weathernext_3_0_0_statistics/zarr/2026_to_present/"
        "20260826_00hr_01_preds/predictions.zarr"
    )
    with pytest.raises(ValueError):
        statistics_run_prefix(
            init_time=init,
            run_directory="20260826_06hr_01_preds",
        )
    with pytest.raises(ValueError):
        statistics_run_prefix(
            init_time=init,
            run_directory="20260826_00hr_preds",
        )


def test_fixture_matches_precomputed_statistics_contract() -> None:
    schema = _schema_fixture()
    assert validate_statistics_schema(schema) == ()
    assert "sample" not in schema["dimensions"]
    assert "lead_subtime" not in schema["dimensions"]

    broken = {**schema, "variables": schema["variables"][:-1]}
    errors = validate_statistics_schema(broken)
    assert errors == ("missing_variable:total_precipitation_1hr_p90",)


def test_selection_plan_is_bounded_sanitized_and_never_uses_full_ensemble() -> None:
    init = datetime(2026, 8, 26, 0, tzinfo=timezone.utc)
    plan = build_statistics_selection_plan(
        init_time=init,
        run_directory="20260826_00hr_01_preds",
        hours_limit=6,
    )
    assert plan["location_id"] == BENCHMARK_LOCATION.id == "station_05480"
    assert plan["bucket"] == GCS_STATISTICS_BUCKET
    assert plan["bucket"] != GCS_FULL_ENSEMBLE_BUCKET
    assert plan["requester_pays"] is False
    assert plan["billing_project_header_required"] is False
    assert plan["lead_time_axis"] == "continuous_1_hour"
    assert plan["lead_hour_start"] == 1
    assert plan["lead_hour_end"] == 6
    assert plan["station_variables"] == list(STATION_STATISTIC_VARIABLES)
    assert plan["surface_variables"] == list(SURFACE_STATISTIC_VARIABLES)
    assert plan["slice_before_materialization"] is True
    assert plan["full_dataset_load_allowed"] is False
    assert plan["full_ensemble_bucket_allowed"] is False
    assert plan["alternate_prefix_fallback_allowed"] is False
    assert plan["coordinates_exposed"] is False
    assert plan["raw_values_exposed"] is False
    assert plan["live_access_performed"] is False
    assert plan["production_write_performed"] is False
    rendered = json.dumps(plan)
    assert "HOME_LAT" not in rendered
    assert "HOME_LON" not in rendered

    with pytest.raises(ValueError):
        build_statistics_selection_plan(
            init_time=init,
            run_directory="20260826_00hr_01_preds",
            hours_limit=25,
        )


def test_fixture_point_records_map_to_existing_forecast_run_provenance() -> None:
    init = datetime(2026, 8, 26, 0, tzinfo=timezone.utc)
    retrieved = datetime(2026, 8, 26, 8, 30, tzinfo=timezone.utc)
    station = [_record(STATION_FIELDS, lead_hour=1)]
    surface = [_record(SURFACE_FIELDS, lead_hour=1)]

    run = statistics_point_records_to_run(
        station,
        surface,
        init_time=init,
        retrieved_at=retrieved,
        run_directory="20260826_00hr_01_preds",
        hours_limit=6,
    )
    assert run.provider == "weathernext3"
    assert run.model_version == "3.0.0"
    assert run.source_surface.startswith("GCS WeatherNext 3 statistics Zarr")
    assert run.transport_provider == "Google Cloud Storage/Zarr"
    assert run.upstream_available_at_utc is None
    assert run.source_metadata["location_id"] == "station_05480"
    assert run.source_metadata["statistics"] == list(STATS)
    assert run.source_metadata["lead_time_axis"] == "continuous_1_hour"
    assert run.source_metadata["full_dataset_load_used"] is False
    assert run.source_metadata["full_ensemble_fallback_used"] is False
    assert run.source_metadata["coordinates_exposed"] is False
    assert run.source_metadata["upstream_available_at_observed"] is False

    temp_mean = next(
        value
        for value in run.values
        if value.variable == "temperature_2m" and value.statistic == "mean"
    )
    assert round(temp_mean.value, 2) == 6.85
    precip_mean = next(
        value
        for value in run.values
        if value.variable == "precipitation_1h" and value.statistic == "mean"
    )
    assert precip_mean.value == 1.0
    assert precip_mean.accumulation_window_minutes == 60


def test_point_mapping_fails_closed_on_missing_statistic_or_mismatched_leads() -> None:
    init = datetime(2026, 8, 26, 0, tzinfo=timezone.utc)
    retrieved = datetime(2026, 8, 26, 8, 30, tzinfo=timezone.utc)
    station = _record(STATION_FIELDS, lead_hour=1)
    station.pop("station_head_temperature_2m_p90")

    with pytest.raises(ValueError, match="missing required statistic"):
        statistics_point_records_to_run(
            [station],
            [_record(SURFACE_FIELDS, lead_hour=1)],
            init_time=init,
            retrieved_at=retrieved,
            run_directory="20260826_00hr_01_preds",
            hours_limit=6,
        )

    with pytest.raises(ValueError, match="lead-hour selections must match"):
        statistics_point_records_to_run(
            [_record(STATION_FIELDS, lead_hour=1)],
            [_record(SURFACE_FIELDS, lead_hour=2)],
            init_time=init,
            retrieved_at=retrieved,
            run_directory="20260826_00hr_01_preds",
            hours_limit=6,
        )
