from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .locations import DWD_10416
from .models import ForecastRun, Observation
from .providers.base import bytes_fetcher, json_fetcher
from .providers.dwd_mosmix import DwdMosmixAdapter
from .providers.dwd_observations import DwdObservationAdapter
from .providers.open_meteo import ECMWF_AIFS, ECMWF_IFS, ICON_D2, OpenMeteoSingleRunAdapter
from .semantics import validate_semantics

def validate_forecast_contract(run: ForecastRun, *, expected_provider: str) -> dict[str, object]:
    errors: list[str] = []
    if run.provider != expected_provider: errors.append("provider_identity_mismatch")
    if not run.values: errors.append("no_supported_values")
    if run.init_time_quality not in {"provider_native", "single_runs_explicit"}: errors.append("weak_init_time_provenance")
    for value in run.values[:200]: errors.extend(validate_semantics(variable=value.variable, value=value.value, unit=value.unit, accumulation_window_minutes=value.accumulation_window_minutes))
    return {"provider": expected_provider, "ok": not errors, "errors": sorted(set(errors)), "model_name": run.model_name, "init_time_quality": run.init_time_quality, "values": len(run.values), "coordinates_exposed": False}

def validate_observation_contract(items: list[Observation]) -> dict[str, object]:
    errors: list[str] = []
    if not items: errors.append("no_observations")
    if items and not any(item.station_id == "10416" and item.location_id == DWD_10416.id for item in items): errors.append("expected_station_10416_missing")
    return {"provider": "dwd_observations", "ok": not errors, "errors": errors, "observations": len(items), "coordinates_exposed": False}

def smoke_public(settings: Settings, *, now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    result: dict[str, Any] = {}
    try:
        run = DwdMosmixAdapter(fetcher=bytes_fetcher(settings.ingest_timeout_seconds)).fetch(retrieved_at=now)
        result["dwd_mosmix_l"] = validate_forecast_contract(run, expected_provider="dwd_mosmix_l")
    except Exception as exc: result["dwd_mosmix_l"] = {"ok": False, "error": type(exc).__name__}
    try:
        observations = DwdObservationAdapter(fetcher=json_fetcher(settings.ingest_timeout_seconds)).fetch(now=now)
        result["dwd_observations"] = validate_observation_contract(observations)
    except Exception as exc: result["dwd_observations"] = {"ok": False, "error": type(exc).__name__}
    for model in (ICON_D2, ECMWF_IFS, ECMWF_AIFS):
        try:
            adapter = OpenMeteoSingleRunAdapter(model, fetcher=json_fetcher(settings.ingest_timeout_seconds))
            metadata = adapter.latest_metadata(now=now)
            run = adapter.fetch(lat=DWD_10416.lat, lon=DWD_10416.lon, init_time=metadata.init_time_utc, availability_time=metadata.availability_time_utc, retrieved_at=now)
            result[model.provider_id] = validate_forecast_contract(run, expected_provider=model.provider_id)
        except Exception as exc: result[model.provider_id] = {"ok": False, "error": type(exc).__name__}
    return result
