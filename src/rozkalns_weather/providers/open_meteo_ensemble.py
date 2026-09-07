from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..models import parse_time, utc_iso
from .base import JsonFetcher, fetch_json

ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
ENSEMBLE_VARIABLES = (
    "temperature_2m",
    "precipitation",
    "pressure_msl",
    "cloud_cover",
    "wind_speed_10m",
    "wind_gusts_10m",
)


@dataclass(frozen=True, slots=True)
class EnsembleModel:
    provider_id: str
    model_provider: str
    model_name: str
    model_key: str
    documented_member_count: int
    role: str = "ensemble"
    strict_run_leaderboard_eligible: bool = False


ICON_D2_EPS = EnsembleModel("icon_d2_eps", "DWD", "ICON-D2-EPS", "dwd_icon_d2_eps", 20)
ECMWF_IFS_ENS = EnsembleModel("ecmwf_ifs_ens", "ECMWF", "IFS ENS 0.25°", "ecmwf_ifs025_ensemble", 51)
ECMWF_AIFS_ENS = EnsembleModel("ecmwf_aifs_ens", "ECMWF", "AIFS ENS 0.25°", "ecmwf_aifs025_ensemble", 51)
WEATHERNEXT2_LEGACY = EnsembleModel(
    "weathernext2_legacy",
    "Google DeepMind",
    "WeatherNext 2",
    "google_weathernext2_ensemble",
    64,
    role="legacy_ai_context",
    strict_run_leaderboard_eligible=False,
)


@dataclass(frozen=True, slots=True)
class EnsemblePoint:
    valid_time_utc: datetime
    variable: str
    member_id: str
    value: float
    unit: str


@dataclass(frozen=True, slots=True)
class EnsembleSnapshot:
    model: EnsembleModel
    retrieved_at_utc: datetime
    points: tuple[EnsemblePoint, ...]
    source_surface: str = "Open-Meteo Ensemble API"
    transport_provider: str = "Open-Meteo"
    source_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def member_ids(self) -> tuple[str, ...]:
        return tuple(sorted({point.member_id for point in self.points}))

    @property
    def member_count(self) -> int:
        return len(self.member_ids)


def _member_id(column: str, variable: str) -> str | None:
    if column == variable:
        return "control"
    prefix = variable + "_member"
    if column.startswith(prefix):
        suffix = column[len(prefix):]
        return f"member{suffix}" if suffix.isdigit() else None
    return None


def parse_ensemble(
    payload: dict[str, Any],
    *,
    model: EnsembleModel,
    retrieved_at: datetime,
    requested_variables: tuple[str, ...] = ENSEMBLE_VARIABLES,
) -> EnsembleSnapshot:
    hourly = payload.get("hourly")
    units = payload.get("hourly_units", {})
    if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
        raise ValueError("Open-Meteo ensemble response has no hourly time series")
    times = hourly["time"]
    points: list[EnsemblePoint] = []
    for variable in requested_variables:
        for column, series in hourly.items():
            member_id = _member_id(str(column), variable)
            if member_id is None or not isinstance(series, list):
                continue
            unit = str(units.get(column) or units.get(variable) or "unknown")
            for timestamp, raw in zip(times, series, strict=False):
                if raw is None:
                    continue
                stamp = str(timestamp)
                valid = parse_time(stamp + ("Z" if "+" not in stamp and not stamp.endswith("Z") else ""))
                points.append(
                    EnsemblePoint(
                        valid_time_utc=valid,
                        variable=variable,
                        member_id=member_id,
                        value=float(raw),
                        unit=unit,
                    )
                )
    if not points:
        raise ValueError("Open-Meteo ensemble response contained no requested member values")
    discovered = sorted({point.member_id for point in points})
    return EnsembleSnapshot(
        model=model,
        retrieved_at_utc=retrieved_at.astimezone(timezone.utc),
        points=tuple(points),
        source_metadata={
            "model_key": model.model_key,
            "model_role": model.role,
            "documented_member_count": model.documented_member_count,
            "discovered_member_count": len(discovered),
            "discovered_member_ids": discovered,
            "individual_member_history_retention_days": 3,
            "retention_semantics": "individual members are short-retention; never fabricate expired historical members",
            "run_provenance": "exact initialization is not exposed by this surface",
            "strict_run_leaderboard_eligible": model.strict_run_leaderboard_eligible,
            "retrieved_at_utc": utc_iso(retrieved_at),
            "generationtime_ms": payload.get("generationtime_ms"),
            "native_timestep_caveat": "Open-Meteo may interpolate ensemble output to hourly resolution",
        },
    )


class OpenMeteoEnsembleAdapter:
    def __init__(self, model: EnsembleModel, *, fetcher: JsonFetcher = fetch_json) -> None:
        self.model = model
        self.fetcher = fetcher

    def fetch(
        self,
        *,
        lat: float,
        lon: float,
        forecast_days: int = 3,
        past_days: int = 0,
        variables: tuple[str, ...] = ENSEMBLE_VARIABLES,
        retrieved_at: datetime | None = None,
    ) -> EnsembleSnapshot:
        if not 1 <= forecast_days <= 16:
            raise ValueError("forecast_days must be between 1 and 16")
        if not 0 <= past_days <= 3:
            raise ValueError("individual member past_days is intentionally bounded to 0..3")
        retrieved_at = (retrieved_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        params = {
            "latitude": lat,
            "longitude": lon,
            "models": self.model.model_key,
            "hourly": ",".join(variables),
            "forecast_days": forecast_days,
            "past_days": past_days,
            "timezone": "UTC",
            "temperature_unit": "celsius",
            "wind_speed_unit": "ms",
            "precipitation_unit": "mm",
        }
        payload = self.fetcher(ENSEMBLE_URL, params)
        return parse_ensemble(payload, model=self.model, retrieved_at=retrieved_at, requested_variables=variables)
