from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
import re
from typing import Any, Iterable, Mapping

from .locations import BENCHMARK_LOCATION
from .models import ForecastRun, ensure_utc
from .providers.weathernext import (
    STATION_FIELDS,
    STATS,
    SURFACE_FIELDS,
    forecast_horizon_hours,
    rows_to_run,
    run_class,
)

GCS_STATISTICS_BUCKET = "weathernext3_statistics_spatial"
GCS_STATISTICS_ROOT = "weathernext_3_0_0_statistics/zarr/2026_to_present"
GCS_ZARR_LEAF = "predictions.zarr"
GCS_FULL_ENSEMBLE_BUCKET = "weathernext3_spatial"
MAX_GCS_FIRST_ACCESS_HOURS = 24
RUN_DIRECTORY_RE = re.compile(
    r"^(?P<date>\\d{8})_(?P<hour>\\d{2})hr_(?P<sequence>\\d{2})_preds$"
)

REQUIRED_COORDINATES = frozenset({
    "init_time",
    "lead_time",
    "lat_0p05",
    "lon_0p05",
    "lat_0p1",
    "lon_0p1",
})
REQUIRED_DIMENSIONS = frozenset({
    "lead_time",
    "lat_0p05",
    "lon_0p05",
    "lat_0p1",
    "lon_0p1",
})
FORBIDDEN_STATISTICS_DIMENSIONS = frozenset({"sample", "lead_subtime"})


def _statistic_variables(fields: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(
        f"{field}_{stat}"
        for field in fields
        for stat in STATS
    )


STATION_STATISTIC_VARIABLES = _statistic_variables(STATION_FIELDS)
SURFACE_STATISTIC_VARIABLES = _statistic_variables(SURFACE_FIELDS)
REQUIRED_STATISTIC_VARIABLES = frozenset(
    STATION_STATISTIC_VARIABLES + SURFACE_STATISTIC_VARIABLES
)


def statistics_run_prefix(*, init_time: datetime, run_directory: str) -> str:
    """Validate one explicit operational run directory and return its Zarr prefix.

    Google documents the run-directory shape but not the meaning of the two-digit
    sequence token. The caller therefore supplies exactly one directory token from
    a separately authorized discovery step; this function never guesses or falls
    back to another token.
    """

    init_time = ensure_utc(init_time)
    if init_time.minute or init_time.second or init_time.microsecond:
        raise ValueError("WeatherNext init_time must be aligned to an exact UTC hour")
    if init_time.year < 2026:
        raise ValueError("operational GCS run paths require 2026_to_present")
    match = RUN_DIRECTORY_RE.fullmatch(run_directory)
    if match is None:
        raise ValueError("invalid WeatherNext GCS run directory")
    expected_date = init_time.strftime("%Y%m%d")
    expected_hour = init_time.strftime("%H")
    if match.group("date") != expected_date or match.group("hour") != expected_hour:
        raise ValueError("WeatherNext GCS run directory does not match init_time")
    return f"{GCS_STATISTICS_ROOT}/{run_directory}/{GCS_ZARR_LEAF}"


def validate_statistics_schema(schema: Mapping[str, Any]) -> tuple[str, ...]:
    coordinates = {str(item) for item in schema.get("coordinates", ())}
    dimensions = {str(item) for item in schema.get("dimensions", ())}
    variables = {str(item) for item in schema.get("variables", ())}

    errors: list[str] = []
    errors.extend(
        f"missing_coordinate:{name}"
        for name in sorted(REQUIRED_COORDINATES - coordinates)
    )
    errors.extend(
        f"missing_dimension:{name}"
        for name in sorted(REQUIRED_DIMENSIONS - dimensions)
    )
    errors.extend(
        f"missing_variable:{name}"
        for name in sorted(REQUIRED_STATISTIC_VARIABLES - variables)
    )
    for name in sorted(FORBIDDEN_STATISTICS_DIMENSIONS & (coordinates | dimensions)):
        errors.append(f"forbidden_statistics_dimension:{name}")
    return tuple(errors)


def build_statistics_selection_plan(
    *,
    init_time: datetime,
    run_directory: str,
    hours_limit: int,
) -> dict[str, object]:
    if type(hours_limit) is not int or not 1 <= hours_limit <= MAX_GCS_FIRST_ACCESS_HOURS:
        raise ValueError("hours_limit must be between 1 and 24")
    prefix = statistics_run_prefix(init_time=init_time, run_directory=run_directory)
    return {
        "schema_version": 1,
        "provider": "weathernext3",
        "model_version": "3.0.0",
        "location_id": BENCHMARK_LOCATION.id,
        "bucket": GCS_STATISTICS_BUCKET,
        "prefix": prefix,
        "requester_pays": False,
        "billing_project_header_required": False,
        "lead_time_axis": "continuous_1_hour",
        "lead_hour_start": 1,
        "lead_hour_end": hours_limit,
        "station_variables": list(STATION_STATISTIC_VARIABLES),
        "surface_variables": list(SURFACE_STATISTIC_VARIABLES),
        "station_grid": "0.05deg",
        "surface_grid": "0.1deg",
        "longitude_convention": "0_to_360",
        "spatial_selection": "nearest_on_declared_grid",
        "slice_before_materialization": True,
        "full_dataset_load_allowed": False,
        "full_ensemble_bucket_allowed": False,
        "alternate_prefix_fallback_allowed": False,
        "coordinates_exposed": False,
        "raw_values_exposed": False,
        "live_access_performed": False,
        "production_write_performed": False,
    }


def _shape_point_records(
    records: Iterable[Mapping[str, Any]],
    *,
    fields: Mapping[str, object],
    init_time: datetime,
    hours_limit: int,
    label: str,
) -> tuple[dict[str, Any], ...]:
    required = tuple(
        f"{field}_{stat}"
        for field in fields
        for stat in STATS
    )
    result: list[dict[str, Any]] = []
    seen_leads: set[int] = set()
    for record in records:
        raw_lead = record.get("lead_hour")
        if type(raw_lead) is not int:
            raise ValueError(f"{label} lead_hour must be an integer")
        lead_hour = int(raw_lead)
        if not 1 <= lead_hour <= hours_limit:
            raise ValueError(f"{label} lead_hour outside bounded first-access window")
        if lead_hour in seen_leads:
            raise ValueError(f"{label} duplicate lead_hour")
        seen_leads.add(lead_hour)

        shaped: dict[str, Any] = {
            "forecast_hour": lead_hour,
            "forecast_time": init_time + timedelta(hours=lead_hour),
        }
        for key in required:
            if key not in record:
                raise ValueError(f"{label} missing required statistic: {key}")
            raw = record[key]
            if raw is None:
                raise ValueError(f"{label} null required statistic: {key}")
            numeric = float(raw)
            if not isfinite(numeric):
                raise ValueError(f"{label} non-finite required statistic: {key}")
            shaped[key] = numeric
        result.append(shaped)
    if not result:
        raise ValueError(f"{label} point records must not be empty")
    result.sort(key=lambda item: int(item["forecast_hour"]))
    return tuple(result)


def statistics_point_records_to_run(
    station_records: Iterable[Mapping[str, Any]],
    surface_records: Iterable[Mapping[str, Any]],
    *,
    init_time: datetime,
    retrieved_at: datetime,
    run_directory: str,
    hours_limit: int,
) -> ForecastRun:
    """Map an already bounded point selection into the existing ForecastRun model.

    This function is intentionally transport-free. A later private GCS gate may
    obtain the selected point records, but source tests can exercise all schema,
    bounding, normalization and provenance semantics without a Google request.
    """

    if type(hours_limit) is not int or not 1 <= hours_limit <= MAX_GCS_FIRST_ACCESS_HOURS:
        raise ValueError("hours_limit must be between 1 and 24")
    init_time = ensure_utc(init_time)
    retrieved_at = ensure_utc(retrieved_at)
    prefix = statistics_run_prefix(init_time=init_time, run_directory=run_directory)
    station = _shape_point_records(
        station_records,
        fields=STATION_FIELDS,
        init_time=init_time,
        hours_limit=hours_limit,
        label="station",
    )
    surface = _shape_point_records(
        surface_records,
        fields=SURFACE_FIELDS,
        init_time=init_time,
        hours_limit=hours_limit,
        label="surface",
    )
    station_leads = {int(row["forecast_hour"]) for row in station}
    surface_leads = {int(row["forecast_hour"]) for row in surface}
    if station_leads != surface_leads:
        raise ValueError("station and surface lead-hour selections must match")

    run05 = rows_to_run(
        station,
        resolution="0p05",
        init_time=init_time,
        retrieved_at=retrieved_at,
    )
    run01 = rows_to_run(
        surface,
        resolution="0p1",
        init_time=init_time,
        retrieved_at=retrieved_at,
    )
    surface_values = tuple(
        value
        for value in run01.values
        if value.variable not in {"temperature_2m", "dew_point_2m"}
    )
    return ForecastRun(
        provider="weathernext3",
        model_provider="Google DeepMind",
        model_name="WeatherNext 3",
        model_version="3.0.0",
        init_time_utc=init_time,
        retrieved_at_utc=retrieved_at,
        source_surface="GCS WeatherNext 3 statistics Zarr 0.05° station + 0.1° surface",
        transport_provider="Google Cloud Storage/Zarr",
        values=tuple(run05.values) + surface_values,
        source_metadata={
            "location_id": BENCHMARK_LOCATION.id,
            "bucket": GCS_STATISTICS_BUCKET,
            "prefix": prefix,
            "requester_pays": False,
            "billing_project_header_used": False,
            "statistics": list(STATS),
            "lead_time_axis": "continuous_1_hour",
            "station_resolution": "0.05deg",
            "surface_resolution": "0.1deg",
            "run_class": run_class(init_time),
            "forecast_horizon_hours": forecast_horizon_hours(init_time),
            "slice_before_materialization": True,
            "full_dataset_load_used": False,
            "full_ensemble_fallback_used": False,
            "coordinates_exposed": False,
            "upstream_available_at_observed": False,
        },
        init_time_quality="provider_native",
        upstream_available_at_utc=None,
    )
