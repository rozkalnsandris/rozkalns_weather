from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ..models import ForecastRun, ForecastValue, parse_time
from .base import JsonFetcher, fetch_json
from .provider_contracts import (
    enforce_contract,
    inspect_open_meteo_metadata,
    inspect_open_meteo_single,
)

SINGLE_RUNS_URL = "https://single-runs-api.open-meteo.com/v1/forecast"
META_URL = "https://api.open-meteo.com/data/{domain}/static/meta.json"
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
    meta_domain: str


ICON_D2 = OpenMeteoModel("icon_d2", "DWD", "ICON-D2", "icon_d2", 2, "dwd_icon_d2")
ECMWF_IFS = OpenMeteoModel("ecmwf_ifs", "ECMWF", "IFS HRES", "ecmwf_ifs", 10, "ecmwf_ifs")
ECMWF_AIFS = OpenMeteoModel("ecmwf_aifs", "ECMWF", "AIFS", "ecmwf_aifs025_single", 15, "ecmwf_aifs025_single")


@dataclass(frozen=True, slots=True)
class ModelRunMetadata:
    init_time_utc: datetime
    availability_time_utc: datetime
    temporal_resolution_seconds: int | None = None
    update_interval_seconds: int | None = None


def _from_unix(value: Any, field: str) -> datetime:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError) as exc:
        raise ValueError(f"Open-Meteo metadata missing/invalid {field}") from exc


def parse_model_metadata(payload: dict[str, Any]) -> ModelRunMetadata:
    enforce_contract(inspect_open_meteo_metadata(payload))
    return ModelRunMetadata(
        init_time_utc=_from_unix(payload.get("last_run_initialisation_time"), "last_run_initialisation_time"),
        availability_time_utc=_from_unix(payload.get("last_run_availability_time"), "last_run_availability_time"),
        temporal_resolution_seconds=int(payload["temporal_resolution_seconds"]) if payload.get("temporal_resolution_seconds") is not None else None,
        update_interval_seconds=int(payload["update_interval_seconds"]) if payload.get("update_interval_seconds") is not None else None,
    )


def parse_open_meteo(
    payload: dict[str, Any],
    *,
    model: OpenMeteoModel,
    retrieved_at: datetime,
    init_time: datetime,
    availability_time: datetime | None,
    requested_variables: tuple[str, ...] = HOURLY_VARIABLES,
) -> ForecastRun:
    contract_report = enforce_contract(
        inspect_open_meteo_single(payload, requested_variables=requested_variables)
    )
    hourly = payload.get("hourly")
    units = payload.get("hourly_units", {})
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        raise ValueError("Open-Meteo response has no hourly time series")
    init_time = init_time.astimezone(timezone.utc)
    availability_time = availability_time.astimezone(timezone.utc) if availability_time else None
    values: list[ForecastValue] = []
    times = hourly["time"]
    for source_key, (variable, normalized_unit, accumulation) in VARIABLE_MAP.items():
        if source_key not in requested_variables:
            continue
        series = hourly.get(source_key)
        if not isinstance(series, list):
            continue
        native_unit = str(units.get(source_key) or normalized_unit)
        for timestamp, raw in zip(times, series, strict=False):
            if raw is None:
                continue
            stamp = str(timestamp)
            valid_time = parse_time(stamp + ("Z" if "+" not in stamp and not stamp.endswith("Z") else ""))
            lead_hours = (valid_time - init_time).total_seconds() / 3600.0
            if lead_hours < 0:
                continue
            values.append(
                ForecastValue(
                    valid_time_utc=valid_time,
                    lead_hours=lead_hours,
                    variable=variable,
                    statistic="deterministic",
                    value=float(raw),
                    unit=normalized_unit,
                    native_value=float(raw),
                    native_unit=native_unit,
                    accumulation_window_minutes=accumulation,
                )
            )
    if not values:
        raise ValueError("Open-Meteo response contained no supported forecast values")
    return ForecastRun(
        provider=model.provider_id,
        model_provider=model.model_provider,
        model_name=model.model_name,
        model_version=None,
        init_time_utc=init_time,
        retrieved_at_utc=retrieved_at,
        upstream_available_at_utc=availability_time,
        init_time_quality="single_runs_explicit",
        source_surface="Open-Meteo Single Runs API",
        transport_provider="Open-Meteo",
        values=tuple(values),
        source_metadata={
            "model_key": model.model_key,
            "meta_domain": model.meta_domain,
            "run_parameter_utc": init_time.strftime("%Y-%m-%dT%H:%M"),
            "upstream_identity_preserved": True,
            "upstream_availability_known": availability_time is not None,
            "historical_backfill": availability_time is None,
            "native_timestep_interpolation_caveat": "Open-Meteo may interpolate model-native timesteps to requested hourly fields",
            "probability_fields_included": False,
            "generationtime_ms": payload.get("generationtime_ms"),
            "provider_contract_drift": contract_report.to_metadata(),
        },
    )


def _params(model: OpenMeteoModel, *, lat: float, lon: float, init_time: datetime) -> dict[str, Any]:
    return {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARIABLES),
        "models": model.model_key,
        "forecast_days": model.forecast_days,
        "run": init_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
        "timezone": "UTC",
        "temperature_unit": "celsius",
        "wind_speed_unit": "ms",
        "precipitation_unit": "mm",
    }


class OpenMeteoSingleRunAdapter:
    def __init__(self, model: OpenMeteoModel, *, fetcher: JsonFetcher = fetch_json) -> None:
        self.model = model
        self.fetcher = fetcher

    def latest_metadata(self, *, now: datetime | None = None) -> ModelRunMetadata:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        payload = self.fetcher(META_URL.format(domain=self.model.meta_domain), {})
        meta = parse_model_metadata(payload)
        if now < meta.availability_time_utc + timedelta(minutes=10):
            raise RuntimeError("latest Open-Meteo run is still within replication safety window")
        return meta

    def fetch(
        self,
        *,
        lat: float,
        lon: float,
        init_time: datetime,
        availability_time: datetime | None,
        retrieved_at: datetime | None = None,
    ) -> ForecastRun:
        retrieved_at = (retrieved_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        init_time = init_time.astimezone(timezone.utc).replace(second=0, microsecond=0)
        availability_time = availability_time.astimezone(timezone.utc) if availability_time else None
        payload = self.fetcher(SINGLE_RUNS_URL, _params(self.model, lat=lat, lon=lon, init_time=init_time))
        return parse_open_meteo(
            payload,
            model=self.model,
            retrieved_at=retrieved_at,
            init_time=init_time,
            availability_time=availability_time,
            requested_variables=HOURLY_VARIABLES,
        )

    def fetch_latest_available(self, *, lat: float, lon: float, now: datetime | None = None) -> ForecastRun:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        meta = self.latest_metadata(now=now)
        return self.fetch(
            lat=lat,
            lon=lon,
            init_time=meta.init_time_utc,
            availability_time=meta.availability_time_utc,
            retrieved_at=now,
        )
