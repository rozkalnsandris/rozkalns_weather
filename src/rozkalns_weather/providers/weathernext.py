from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from ..models import ForecastRun, ForecastValue, parse_time

STATS = ("mean", "p10", "p25", "p50", "p75", "p90")

SURFACE_FIELDS = {
    "temperature_2m": ("temperature_2m", "K", "degC", None),
    "dewpoint_temperature_2m": ("dew_point_2m", "K", "degC", None),
    "wind_speed_10m": ("wind_speed_10m", "m/s", "m/s", None),
    "mean_sea_level_pressure": ("pressure_msl", "Pa", "hPa", None),
    "total_cloud_cover": ("cloud_cover", "fraction", "%", None),
    "total_precipitation_1hr": ("precipitation_1h", "m", "mm", 60),
}

STATION_FIELDS = {
    "station_head_temperature_2m": ("temperature_2m", "K", "degC", None),
    "station_head_dewpoint_temperature_2m": ("dew_point_2m", "K", "degC", None),
}


def run_class(init_time: datetime) -> str:
    return "synoptic_360h" if init_time.astimezone(timezone.utc).hour in {0, 6, 12, 18} else "interim_48h"


def forecast_horizon_hours(init_time: datetime) -> int:
    return 360 if run_class(init_time) == "synoptic_360h" else 48


def _convert(value: float, native_unit: str, unit: str) -> float:
    if native_unit == "K" and unit == "degC":
        return value - 273.15
    if native_unit == "Pa" and unit == "hPa":
        return value / 100.0
    if native_unit == "m" and unit == "mm":
        return value * 1000.0
    if native_unit == "fraction" and unit == "%":
        return value * 100.0
    return value


def rows_to_run(
    rows: Iterable[Mapping[str, Any]],
    *,
    resolution: str,
    init_time: datetime,
    retrieved_at: datetime,
) -> ForecastRun:
    """Normalize already-selected WeatherNext statistics into the common model."""

    if resolution not in {"0p05", "0p1"}:
        raise ValueError("resolution must be 0p05 or 0p1")

    fields = STATION_FIELDS if resolution == "0p05" else SURFACE_FIELDS
    values: list[ForecastValue] = []

    for row in rows:
        valid_time = row.get("forecast_time")
        if isinstance(valid_time, str):
            valid = parse_time(valid_time)
        elif isinstance(valid_time, datetime):
            valid = valid_time.astimezone(timezone.utc)
        else:
            continue

        raw_lead = row.get("forecast_hour")
        lead = float(
            raw_lead
            if raw_lead is not None
            else (valid - init_time.astimezone(timezone.utc)).total_seconds() / 3600.0
        )

        for field, (variable, native_unit, unit, accumulation) in fields.items():
            for statistic in STATS:
                raw = row.get(f"{field}_{statistic}")
                if raw is None:
                    continue
                native_value = float(raw)
                values.append(
                    ForecastValue(
                        valid_time_utc=valid,
                        lead_hours=lead,
                        variable=variable,
                        statistic=statistic,
                        value=_convert(native_value, native_unit, unit),
                        unit=unit,
                        native_value=native_value,
                        native_unit=native_unit,
                        accumulation_window_minutes=accumulation,
                    )
                )

    return ForecastRun(
        provider="weathernext3",
        model_provider="Google DeepMind",
        model_name="WeatherNext 3",
        model_version="3.0.0",
        init_time_utc=init_time,
        retrieved_at_utc=retrieved_at,
        source_surface=f"WeatherNext 3 normalized statistics {resolution}",
        transport_provider="internal-normalization",
        values=tuple(values),
        source_metadata={
            "resolution": resolution,
            "statistics": list(STATS),
            "run_class": run_class(init_time),
            "forecast_horizon_hours": forecast_horizon_hours(init_time),
        },
        init_time_quality="provider_native",
        upstream_available_at_utc=None,
    )
