from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any

from ..models import ForecastRun, ForecastValue, parse_time
from .base import JsonFetcher, fetch_json

ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
MEMBER_RETENTION = timedelta(days=3)
_MEMBER_RE = re.compile(r"^(?P<variable>[a-z0-9_]+)_member(?P<member>[0-9]+)$")


@dataclass(frozen=True, slots=True)
class EnsembleModel:
    provider_id: str
    model_provider: str
    model_name: str
    model_key: str
    expected_members: int
    forecast_days: int
    role: str
    native_timestep_hours: int


ICON_D2_EPS = EnsembleModel("icon_d2_eps", "DWD", "ICON-D2-EPS", "icon_d2_eps", 20, 2, "probabilistic_baseline", 1)
ECMWF_IFS_ENS = EnsembleModel("ecmwf_ifs_ens", "ECMWF", "IFS ENS 0.25°", "ecmwf_ifs025_ensemble", 51, 15, "probabilistic_baseline", 3)
ECMWF_AIFS_ENS = EnsembleModel("ecmwf_aifs_ens", "ECMWF", "AIFS ENS 0.25°", "ecmwf_aifs025_ensemble", 51, 15, "probabilistic_ai_baseline", 6)
WEATHERNEXT2 = EnsembleModel("weathernext2", "Google", "WeatherNext 2", "google_weathernext2_ensemble", 64, 15, "legacy_ai_context", 6)
ENSEMBLE_MODELS = (ICON_D2_EPS, ECMWF_IFS_ENS, ECMWF_AIFS_ENS, WEATHERNEXT2)

VARIABLE_MAP = {
    "temperature_2m": ("temperature_2m", "degC", None),
    "precipitation": ("precipitation_1h", "mm", 60),
    "wind_speed_10m": ("wind_speed_10m", "m/s", None),
    "wind_gusts_10m": ("wind_gust_10m", "m/s", None),
}


def member_retention_state(*, init_time: datetime, now: datetime | None = None) -> str:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    init_time = init_time.astimezone(timezone.utc)
    return "members_available" if now - init_time <= MEMBER_RETENTION else "members_expired_mean_spread_only"


def parse_ensemble(payload: dict[str, Any], *, model: EnsembleModel, retrieved_at: datetime, init_time: datetime | None = None) -> ForecastRun:
    hourly = payload.get("hourly")
    units = payload.get("hourly_units", {})
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        raise ValueError("Open-Meteo ensemble response has no hourly time series")
    times = hourly["time"]
    explicit_init = init_time is not None
    init = (init_time or parse_time(str(times[0]) + ("Z" if not str(times[0]).endswith("Z") else ""))).astimezone(timezone.utc)
    values: list[ForecastValue] = []
    members_seen: set[int] = set()
    for key, series in hourly.items():
        match = _MEMBER_RE.match(str(key))
        if not match or not isinstance(series, list):
            continue
        source_variable = match.group("variable")
        if source_variable not in VARIABLE_MAP:
            continue
        member = int(match.group("member"))
        members_seen.add(member)
        variable, unit, accumulation = VARIABLE_MAP[source_variable]
        native_unit = str(units.get(key) or unit)
        for timestamp, raw in zip(times, series, strict=False):
            if raw is None:
                continue
            stamp = str(timestamp)
            valid_time = parse_time(stamp + ("Z" if "+" not in stamp and not stamp.endswith("Z") else ""))
            lead = (valid_time - init).total_seconds() / 3600.0
            if lead < 0:
                continue
            values.append(ForecastValue(valid_time_utc=valid_time, lead_hours=lead, variable=variable, statistic=f"member_{member:02d}", value=float(raw), unit=unit, native_value=float(raw), native_unit=native_unit, accumulation_window_minutes=accumulation, quality_status="ensemble_member"))
    if not values:
        raise ValueError("Open-Meteo ensemble response contained no supported member fields")
    return ForecastRun(
        provider=model.provider_id,
        model_provider=model.model_provider,
        model_name=model.model_name,
        model_version=None,
        init_time_utc=init,
        retrieved_at_utc=retrieved_at.astimezone(timezone.utc),
        source_surface="Open-Meteo Ensemble API",
        transport_provider="Open-Meteo",
        init_time_quality="provider_native" if explicit_init else "ensemble_surface_time_axis_not_native_init",
        values=tuple(values),
        source_metadata={
            "model_key": model.model_key,
            "role": model.role,
            "expected_members": model.expected_members,
            "members_seen": sorted(members_seen),
            "member_count": len(members_seen),
            "member_retention_days": MEMBER_RETENTION.days,
            "native_timestep_hours": model.native_timestep_hours,
            "api_interpolates_to_hourly_by_default": True,
            "strict_run_to_run_eligible": explicit_init and model.role != "legacy_ai_context",
            "generationtime_ms": payload.get("generationtime_ms"),
        },
    )


def _params(model: EnsembleModel, *, lat: float, lon: float, forecast_days: int | None = None) -> dict[str, Any]:
    return {"latitude": lat, "longitude": lon, "hourly": ",".join(VARIABLE_MAP), "models": model.model_key, "forecast_days": min(model.forecast_days, forecast_days or model.forecast_days), "timezone": "UTC", "temperature_unit": "celsius", "wind_speed_unit": "ms", "precipitation_unit": "mm"}


class OpenMeteoEnsembleAdapter:
    def __init__(self, model: EnsembleModel, *, fetcher: JsonFetcher = fetch_json) -> None:
        self.model = model
        self.fetcher = fetcher

    def fetch(self, *, lat: float, lon: float, retrieved_at: datetime | None = None, forecast_days: int | None = None, init_time: datetime | None = None) -> ForecastRun:
        retrieved_at = (retrieved_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        payload = self.fetcher(ENSEMBLE_URL, _params(self.model, lat=lat, lon=lon, forecast_days=forecast_days))
        return parse_ensemble(payload, model=self.model, retrieved_at=retrieved_at, init_time=init_time)
