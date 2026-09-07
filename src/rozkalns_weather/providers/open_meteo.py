from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..models import ForecastRun, ForecastValue, parse_time
from .base import JsonFetcher, fetch_json

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARIABLES = (
    "temperature_2m",
    "dew_point_2m",
    "precipitation",
    "pressure_msl",
    "cloud_cover",
    "wind_speed_10m",
    "wind_gusts_10m",
)

VARIABLE_MAP = {
    "temperature_2m": ("temperature_2m", "degC", None),
    "dew_point_2m": ("dew_point_2m", "degC", None),
    "precipitation": ("precipitation_1h", "mm", 60),
    "pressure_msl": ("pressure_msl", "hPa", None),
    "cloud_cover": ("cloud_cover", "%", None),
    "wind_speed_10m": ("wind_speed_10m", "m/s", None),
    "wind_gusts_10m": ("wind_gust_10m", "m/s", None),
}


@dataclass(frozen=True, slots=True)
class OpenMeteoModel:
    provider_id: str
    model_provider: str
    model_name: str
    model_key: str
    forecast_days: int


ICON_D2 = OpenMeteoModel("icon_d2", "DWD", "ICON-D2", "icon_d2", 2)
ECMWF_IFS = OpenMeteoModel("ecmwf_ifs", "ECMWF", "IFS HRES", "ecmwf_ifs", 15)
ECMWF_AIFS = OpenMeteoModel("ecmwf_aifs", "ECMWF", "AIFS", "ecmwf_aifs025_single", 15)


def _parse_generation_init(payload: dict[str, Any], retrieved_at: datetime) -> datetime:
    # The current forecast endpoint does not expose a stable upstream init timestamp in every response.
    return retrieved_at.replace(minute=0, second=0, microsecond=0)


def parse_open_meteo(payload: dict[str, Any], *, model: OpenMeteoModel, retrieved_at: datetime) -> ForecastRun:
    hourly = payload.get("hourly")
    units = payload.get("hourly_units", {})
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        raise ValueError("Open-Meteo response has no hourly time series")

    init_time = _parse_generation_init(payload, retrieved_at)
    values: list[ForecastValue] = []
    times = hourly["time"]
    for source_key, (variable, normalized_unit, accumulation) in VARIABLE_MAP.items():
        series = hourly.get(source_key)
        if not isinstance(series, list):
            continue
        native_unit = str(units.get(source_key) or normalized_unit)
        for timestamp, raw in zip(times, series, strict=False):
            if raw is None:
                continue
            stamp = str(timestamp)
            valid_time = parse_time(stamp + ("Z" if "+" not in stamp and not stamp.endswith("Z") else ""))
            if valid_time < retrieved_at.replace(minute=0, second=0, microsecond=0):
                continue
            lead_hours = max(0.0, (valid_time - init_time).total_seconds() / 3600.0)
            values.append(ForecastValue(valid_time_utc=valid_time, lead_hours=lead_hours, variable=variable, statistic="deterministic", value=float(raw), unit=normalized_unit, native_value=float(raw), native_unit=native_unit, accumulation_window_minutes=accumulation))

    return ForecastRun(
        provider=model.provider_id,
        model_provider=model.model_provider,
        model_name=model.model_name,
        model_version=None,
        init_time_utc=init_time,
        retrieved_at_utc=retrieved_at,
        source_surface="Open-Meteo Forecast API",
        transport_provider="Open-Meteo",
        values=tuple(values),
        source_metadata={"model_key": model.model_key, "upstream_identity_preserved": True, "init_time_quality": "retrieval_hour_proxy", "generationtime_ms": payload.get("generationtime_ms")},
    )


class OpenMeteoAdapter:
    def __init__(self, model: OpenMeteoModel, *, fetcher: JsonFetcher = fetch_json) -> None:
        self.model = model
        self.fetcher = fetcher

    def fetch(self, *, lat: float, lon: float, retrieved_at: datetime | None = None) -> ForecastRun:
        retrieved_at = (retrieved_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        params: dict[str, Any] = {"latitude": lat, "longitude": lon, "hourly": ",".join(HOURLY_VARIABLES), "models": self.model.model_key, "forecast_days": self.model.forecast_days, "timezone": "UTC", "temperature_unit": "celsius", "wind_speed_unit": "ms", "precipitation_unit": "mm"}
        return parse_open_meteo(self.fetcher(OPEN_METEO_URL, params), model=self.model, retrieved_at=retrieved_at)
