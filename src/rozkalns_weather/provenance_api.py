from __future__ import annotations

from collections.abc import Mapping

from .db import Database
from .value_provenance import (
    ValueProvenanceError,
    build_verification_value_trace,
    forecast_trace_evidence,
)


def hourly_with_provenance(
    database: Database,
    *,
    hours: int = 48,
    variable: str = "temperature_2m",
    location_id: str = "home",
) -> list[dict[str, object]]:
    """Return the existing latest-hourly surface with a privacy-safe trace per value."""
    if not 1 <= hours <= 360:
        raise ValueError("hours must be between 1 and 360")
    with database.connect() as connection:
        rows = connection.execute(
            """WITH latest AS (
                SELECT provider,location_id,MAX(retrieved_at_utc) AS retrieved_at_utc
                FROM forecast_runs WHERE location_id=? GROUP BY provider,location_id
            ) SELECT r.provider,r.model_provider,r.model_name,r.model_version,r.location_id,
                     r.init_time_utc,r.init_time_quality,r.upstream_available_at_utc,r.retrieved_at_utc,
                     r.source_surface,r.transport_provider,r.raw_payload_hash,r.revision,
                     v.valid_time_utc,v.lead_hours,v.variable,v.statistic,v.value,v.unit,
                     v.native_value,v.native_unit,v.accumulation_window_minutes,v.quality_status
              FROM latest l JOIN forecast_runs r
                ON r.provider=l.provider AND r.location_id=l.location_id
               AND r.retrieved_at_utc=l.retrieved_at_utc
              JOIN forecast_values v ON v.run_id=r.id
              WHERE v.variable=? AND v.lead_hours<=?
              ORDER BY v.valid_time_utc,r.provider,v.statistic""",
            (location_id, variable, hours),
        ).fetchall()
    output: list[dict[str, object]] = []
    for raw in rows:
        row = dict(raw)
        row["provenance_trace"] = forecast_trace_evidence(row)
        output.append(row)
    return output


def verification_value_trace(
    database: Database,
    *,
    provider: str,
    valid_time_utc: str,
    variable: str,
    statistic: str = "deterministic",
    metric_name: str = "absolute_error",
) -> dict[str, object]:
    """Trace one canonical station_05480 verification value without mutating corpus state."""
    with database.connect() as connection:
        forecast = connection.execute(
            """SELECT r.provider,r.model_provider,r.model_name,r.model_version,r.location_id,
                      r.init_time_utc,r.init_time_quality,r.upstream_available_at_utc,r.retrieved_at_utc,
                      r.source_surface,r.transport_provider,r.raw_payload_hash,r.revision,
                      v.valid_time_utc,v.lead_hours,v.variable,v.statistic,v.value,v.unit,
                      v.native_value,v.native_unit,v.accumulation_window_minutes,v.quality_status
               FROM forecast_runs r JOIN forecast_values v ON v.run_id=r.id
               WHERE r.location_id='station_05480' AND r.provider=? AND v.valid_time_utc=?
                 AND v.variable=? AND v.statistic=?
               ORDER BY r.revision DESC,r.retrieved_at_utc DESC LIMIT 1""",
            (provider, valid_time_utc, variable, statistic),
        ).fetchone()
        truth = connection.execute(
            """SELECT source_provider,station_id,location_id,observed_at_utc,variable,value,unit,quality_status
               FROM observations
               WHERE source_provider='DWD' AND station_id='05480' AND location_id='station_05480'
                 AND observed_at_utc=? AND variable=?
               ORDER BY id DESC LIMIT 1""",
            (valid_time_utc, variable),
        ).fetchone()
    if forecast is None:
        raise ValueProvenanceError("FORECAST_VALUE_NOT_FOUND", "no matching station_05480 forecast value exists")
    if truth is None:
        raise ValueProvenanceError("TRUTH_VALUE_NOT_FOUND", "no matching DWD CDC 05480 truth value exists")
    return build_verification_value_trace(
        dict(forecast),
        dict(truth),
        metric_identity={
            "name": metric_name,
            "version": 1,
            "comparison_mode": "station_run_skill",
            "location_id": "station_05480",
        },
    )


def blocked_trace_response(exc: Exception) -> dict[str, object]:
    return {
        "contract": "value-provenance-trace-v1",
        "schema_version": 1,
        "state": "BLOCKED",
        "reason_codes": [getattr(exc, "reason_code", "INVALID_TRACE_REQUEST")],
        "privacy": {
            "coordinates_exposed": False,
            "database_path_exposed": False,
            "credentials_exposed": False,
            "raw_logs_exposed": False,
        },
    }
