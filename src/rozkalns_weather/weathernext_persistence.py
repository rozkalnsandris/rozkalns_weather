from __future__ import annotations

from datetime import datetime
from typing import Mapping

from .db import Database
from .locations import BENCHMARK_LOCATION
from .weathernext_canary import WeatherNextGCSCanaryError, read_fixed_snapshot


class WeatherNextGCSPersistenceError(RuntimeError):
    pass


def persist_fixed_snapshot(
    *,
    init_time: datetime,
    database: Database,
) -> Mapping[str, object]:
    """Read one validated WeatherNext snapshot and atomically persist its ForecastRun."""

    try:
        result = read_fixed_snapshot(init_time)
    except WeatherNextGCSCanaryError as exc:
        raise WeatherNextGCSPersistenceError(
            "WeatherNext GCS snapshot read failed closed"
        ) from exc

    run = result.run
    if run.provider != "weathernext3" or run.init_time_utc != init_time:
        raise WeatherNextGCSPersistenceError(
            "WeatherNext GCS snapshot identity failed closed"
        )

    try:
        database.insert_forecast_run(
            run,
            location_id=BENCHMARK_LOCATION.id,
        )
    except Exception as exc:
        raise WeatherNextGCSPersistenceError(
            "WeatherNext GCS snapshot persistence failed closed"
        ) from exc

    evidence = dict(result.evidence)
    return {
        "state": "weathernext_snapshot_persisted",
        "provider": run.provider,
        "model_version": run.model_version,
        "location_id": BENCHMARK_LOCATION.id,
        "selected_init_time_utc": evidence["selected_init_time_utc"],
        "lead_count": evidence["lead_count"],
        "source_materialized_scalar_count": evidence["materialized_scalar_count"],
        "persisted_value_count": len(run.values),
        "schema_valid": evidence["schema_valid"],
        "provenance_complete": evidence["provenance_complete"],
        "automatic_retry_used": evidence["automatic_retry_used"],
        "full_dataset_load_used": evidence["full_dataset_load_used"],
        "full_ensemble_fallback_used": evidence["full_ensemble_fallback_used"],
        "raw_values_exposed": False,
        "coordinates_exposed": False,
        "production_write_performed": True,
    }
