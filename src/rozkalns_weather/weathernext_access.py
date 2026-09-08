from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable, Iterable, Mapping

from .config import Settings
from .locations import DWD_10416
from .models import ForecastRun
from .providers.weathernext import (
    EXPECTED_SCHEMA,
    STATS,
    TABLE_005,
    TABLE_01,
    WeatherNextDataLatency,
    WeatherNextBigQueryAdapter,
    available_init_candidates,
    build_point_query,
    forecast_horizon_hours,
    run_class,
    validate_query_contract,
    validate_schema_rows,
)

ACCESS_STATES = frozenset({
    "access_pending", "linked_dataset_ready", "permission_denied", "dataset_unlinked",
    "schema_changed", "data_latency", "cost_cap_rejected", "ready_for_canary",
    "canary_ready_for_snapshot",
})
FIRST_ACCESS_STAGES = (
    "linked_dataset_probe", "schema_fingerprint", "dry_run_cost_guard",
    "bounded_canary_query", "provenance_validate", "first_snapshot_write",
)
MAX_CANARY_HOURS = 24
MAX_ALLOWED_BYTES_BILLED = 1_073_741_824
DEFAULT_CANARY_HOURS = 6
PRIVATE_EVIDENCE_KEYS = frozenset({
    "project", "project_id", "google_cloud_project", "dataset", "dataset_id",
    "weathernext_bigquery_dataset", "credential", "credentials", "token", "secret",
    "service_account", "home_lat", "home_lon", "latitude", "longitude", "lat", "lon",
    "sql", "query_sql", "database_path", "filesystem_path", "host_path", "raw_log",
    "raw_logs", "environment", "env",
})


class WeatherNextCostLimit(RuntimeError):
    """A dry-run estimate or configured query exceeds the explicit bytes cap."""


@dataclass(frozen=True, slots=True)
class DryRunEvidence:
    resolution: str
    estimated_bytes: int
    maximum_bytes_billed: int

    @property
    def within_cap(self) -> bool:
        return self.estimated_bytes <= self.maximum_bytes_billed

    def as_dict(self) -> dict[str, object]:
        return {
            "resolution": self.resolution,
            "estimated_bytes": self.estimated_bytes,
            "maximum_bytes_billed": self.maximum_bytes_billed,
            "within_cap": self.within_cap,
        }


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_hash(lines: Iterable[str]) -> str:
    payload = "\n".join(sorted(lines)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def expected_required_schema_fingerprint() -> str:
    return _stable_hash(
        f"{table}:{path}" for table in sorted(EXPECTED_SCHEMA)
        for path in sorted(EXPECTED_SCHEMA[table])
    )


def schema_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, object]:
    materialized = [dict(row) for row in rows]
    errors = validate_schema_rows(materialized)
    observed: dict[str, set[str]] = {TABLE_005: set(), TABLE_01: set()}
    for row in materialized:
        table = str(row.get("table_name") or "")
        path = str(row.get("field_path") or row.get("column_name") or "")
        if table in observed and path:
            observed[table].add(path)
    required_present = [
        f"{table}:{path}" for table in sorted(EXPECTED_SCHEMA)
        for path in sorted(observed[table] & EXPECTED_SCHEMA[table])
    ]
    observed_all = [
        f"{table}:{path}" for table in sorted(observed)
        for path in sorted(observed[table])
    ]
    return {
        "state": "linked_dataset_ready" if not errors else "schema_changed",
        "schema_errors": list(errors),
        "expected_required_fingerprint": expected_required_schema_fingerprint(),
        "observed_required_fingerprint": _stable_hash(required_present),
        "observed_full_fingerprint": _stable_hash(observed_all),
        "required_path_count": sum(len(paths) for paths in EXPECTED_SCHEMA.values()),
        "observed_required_path_count": len(required_present),
        "observed_path_count": len(observed_all),
        "table_contract": [TABLE_005, TABLE_01],
    }


def classify_access_error(exc: Exception) -> str:
    if isinstance(exc, WeatherNextDataLatency):
        return "data_latency"
    text = f"{type(exc).__name__} {exc}".lower()
    if any(token in text for token in ("forbidden", "permission denied", "access denied", "403")):
        return "permission_denied"
    if "dataset" in text and any(token in text for token in ("not found", "404", "unlinked", "linked dataset")):
        return "dataset_unlinked"
    if any(token in text for token in ("unrecognized name", "no such field", "missing field", "column not found", "table not found")):
        return "schema_changed"
    return "access_pending"


def _validate_canary_bounds(*, hours_limit: int, maximum_bytes_billed: int) -> None:
    if not 1 <= hours_limit <= MAX_CANARY_HOURS:
        raise ValueError(f"hours_limit must be between 1 and {MAX_CANARY_HOURS}")
    if not 1 <= maximum_bytes_billed <= MAX_ALLOWED_BYTES_BILLED:
        raise ValueError(f"maximum_bytes_billed must be between 1 and {MAX_ALLOWED_BYTES_BILLED}")


def build_canary_plan(*, now: datetime, hours_limit: int = DEFAULT_CANARY_HOURS,
                      maximum_bytes_billed: int, init_time: datetime | None = None) -> dict[str, object]:
    _validate_canary_bounds(hours_limit=hours_limit, maximum_bytes_billed=maximum_bytes_billed)
    now = now.astimezone(timezone.utc)
    candidates = available_init_candidates(now, limit=24)
    if init_time is None:
        if not candidates:
            raise WeatherNextDataLatency("no WeatherNext init fits the expected dissemination window")
        init_time = candidates[0]
    init_time = init_time.astimezone(timezone.utc)
    if init_time not in candidates:
        raise WeatherNextDataLatency("selected init is outside the target-disseminated candidate set")
    horizon = forecast_horizon_hours(init_time)
    if hours_limit > horizon:
        raise ValueError("hours_limit exceeds selected WeatherNext run horizon")
    return {
        "schema_version": 1, "state": "ready_for_canary", "provider": "weathernext3",
        "model_name": "WeatherNext 3", "model_version_contract": "3.0.0",
        "location_id": DWD_10416.id, "selected_init_time_utc": _utc_iso(init_time),
        "run_class": run_class(init_time), "forecast_horizon_hours": horizon,
        "hours_limit": hours_limit, "maximum_bytes_billed_per_query": maximum_bytes_billed,
        "dry_run_required": True,
        "surfaces": [
            {"resolution": "0p05", "table": TABLE_005, "role": "station"},
            {"resolution": "0p1", "table": TABLE_01, "role": "surface"},
        ],
        "real_query_performed": False, "production_write_eligible": False,
        "coordinates_exposed": False, "credentials_exposed": False,
    }


def _default_job_config(*, dry_run: bool, maximum_bytes_billed: int) -> Any:
    try:
        from google.cloud import bigquery  # type: ignore
    except ImportError as exc:
        raise RuntimeError("WeatherNext BigQuery access requires the optional 'weathernext' dependency") from exc
    config = bigquery.QueryJobConfig()
    config.dry_run = dry_run
    config.use_query_cache = False
    config.maximum_bytes_billed = maximum_bytes_billed
    return config


def _query_pair(*, project: str, dataset: str, lat: float, lon: float,
                init_time: datetime, hours_limit: int) -> tuple[object, object]:
    q05 = build_point_query(project=project, dataset=dataset, lat=lat, lon=lon,
                            init_time=init_time, resolution="0p05", hours_limit=hours_limit)
    q01 = build_point_query(project=project, dataset=dataset, lat=lat, lon=lon,
                            init_time=init_time, resolution="0p1", hours_limit=hours_limit)
    for query in (q05, q01):
        errors = validate_query_contract(query)
        if errors:
            raise ValueError("invalid WeatherNext canary query contract: " + ",".join(errors))
    return q05, q01


def dry_run_canary_queries(*, client: Any, project: str, dataset: str, lat: float, lon: float,
                           init_time: datetime, hours_limit: int, maximum_bytes_billed: int,
                           job_config_factory: Callable[..., Any] | None = None) -> tuple[DryRunEvidence, DryRunEvidence]:
    _validate_canary_bounds(hours_limit=hours_limit, maximum_bytes_billed=maximum_bytes_billed)
    factory = job_config_factory or _default_job_config
    q05, q01 = _query_pair(project=project, dataset=dataset, lat=lat, lon=lon,
                           init_time=init_time, hours_limit=hours_limit)
    evidence: list[DryRunEvidence] = []
    for query in (q05, q01):
        config = factory(dry_run=True, maximum_bytes_billed=maximum_bytes_billed)
        job = client.query(query.sql, job_config=config)
        estimated = int(getattr(job, "total_bytes_processed", 0) or 0)
        item = DryRunEvidence(query.resolution, estimated, maximum_bytes_billed)
        if not item.within_cap:
            raise WeatherNextCostLimit(f"{query.resolution} dry-run estimate exceeds maximum_bytes_billed")
        evidence.append(item)
    return evidence[0], evidence[1]


def validate_canary_rows(rows05: Iterable[Mapping[str, Any]], rows01: Iterable[Mapping[str, Any]]) -> dict[str, object]:
    station_rows = [dict(row) for row in rows05]
    surface_rows = [dict(row) for row in rows01]
    station_temperature = any(row.get("station_head_temperature_2m_mean") is not None for row in station_rows)
    station_dewpoint = any(row.get("station_head_dewpoint_temperature_2m_mean") is not None for row in station_rows)
    surface_keys = ("wind_speed_10m_mean", "mean_sea_level_pressure_mean", "total_cloud_cover_mean", "total_precipitation_1hr_mean")
    surface_output = any(any(row.get(key) is not None for key in surface_keys) for row in surface_rows)
    complete = bool(station_rows and surface_rows and station_temperature and station_dewpoint and surface_output)
    return {
        "state": "canary_complete" if complete else "empty_canary",
        "station_row_count": len(station_rows), "surface_row_count": len(surface_rows),
        "station_temperature_present": station_temperature, "station_dewpoint_present": station_dewpoint,
        "surface_output_present": surface_output, "product_surfaces_complete": complete,
        "values_exposed": False,
    }


def execute_canary_queries(*, client: Any, project: str, dataset: str, lat: float, lon: float,
                           init_time: datetime, hours_limit: int, maximum_bytes_billed: int,
                           dry_run_evidence: Iterable[DryRunEvidence],
                           job_config_factory: Callable[..., Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _validate_canary_bounds(hours_limit=hours_limit, maximum_bytes_billed=maximum_bytes_billed)
    checked = tuple(dry_run_evidence)
    if len(checked) != 2 or any(item.maximum_bytes_billed != maximum_bytes_billed or not item.within_cap for item in checked):
        raise WeatherNextCostLimit("successful matching dry-run evidence is required before canary query")
    factory = job_config_factory or _default_job_config
    q05, q01 = _query_pair(project=project, dataset=dataset, lat=lat, lon=lon,
                           init_time=init_time, hours_limit=hours_limit)
    rows: list[list[dict[str, Any]]] = []
    for query in (q05, q01):
        config = factory(dry_run=False, maximum_bytes_billed=maximum_bytes_billed)
        job = client.query(query.sql, job_config=config)
        rows.append([dict(row) for row in job.result()])
    return rows[0], rows[1]


def validate_provenance(run: ForecastRun) -> dict[str, object]:
    errors: list[str] = []
    if run.provider != "weathernext3": errors.append("provider")
    if run.model_provider != "Google DeepMind": errors.append("model_provider")
    if run.model_name != "WeatherNext 3": errors.append("model_name")
    if run.model_version != "3.0.0": errors.append("model_version")
    if run.transport_provider != "Google BigQuery": errors.append("transport_provider")
    if not run.source_surface.startswith("BigQuery WeatherNext 3"): errors.append("source_surface")
    metadata = run.source_metadata
    required_metadata = {"statistics", "run_class", "forecast_horizon_hours", "expected_available_at_utc"}
    if not required_metadata.issubset(metadata): errors.append("source_metadata")
    if tuple(metadata.get("statistics") or ()) != STATS: errors.append("statistics_metadata")
    if metadata.get("run_class") != run_class(run.init_time_utc): errors.append("run_class")
    if metadata.get("forecast_horizon_hours") != forecast_horizon_hours(run.init_time_utc): errors.append("forecast_horizon_hours")
    if run.upstream_available_at_utc is not None and not metadata.get("upstream_available_at_observed", False):
        errors.append("unverified_upstream_available_at")
    if not run.values: errors.append("values")
    observed_stats = {value.statistic for value in run.values}
    if not set(STATS).issubset(observed_stats): errors.append("statistics_values")
    for value in run.values:
        if value.statistic not in STATS:
            errors.append("unexpected_statistic"); break
        expected_lead = (value.valid_time_utc - run.init_time_utc).total_seconds() / 3600.0
        if abs(value.lead_hours - expected_lead) > 1e-6:
            errors.append("lead_hours"); break
    for value in run.values:
        if value.variable == "precipitation_1h" and value.accumulation_window_minutes != 60:
            errors.append("precipitation_accumulation"); break
    return {
        "state": "complete" if not errors else "invalid", "complete": not errors,
        "errors": sorted(set(errors)), "provider": "weathernext3", "model_version": run.model_version,
        "init_time_utc": _utc_iso(run.init_time_utc), "retrieved_at_utc": _utc_iso(run.retrieved_at_utc),
        "run_class": run_class(run.init_time_utc), "forecast_horizon_hours": forecast_horizon_hours(run.init_time_utc),
        "statistics": list(STATS), "real_values_exposed": False, "coordinates_exposed": False,
    }


def _find_private_key(value: object, *, path: str = "") -> str | None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).lower()
            child_path = f"{path}.{key}" if path else key
            if key in PRIVATE_EVIDENCE_KEYS: return child_path
            found = _find_private_key(child, path=child_path)
            if found: return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _find_private_key(child, path=f"{path}[{index}]")
            if found: return found
    return None


def validate_first_access_evidence(evidence: Mapping[str, Any]) -> dict[str, object]:
    private_key = _find_private_key(evidence)
    if private_key: raise ValueError(f"private evidence field forbidden: {private_key}")
    state = str(evidence.get("state") or "")
    if state not in ACCESS_STATES: raise ValueError("unknown first-access evidence state")
    schema = evidence.get("schema")
    if not isinstance(schema, Mapping): raise ValueError("schema evidence is required")
    if schema.get("state") != "linked_dataset_ready": raise ValueError("linked dataset/schema must be ready")
    dry_run = evidence.get("dry_run")
    if not isinstance(dry_run, list) or len(dry_run) != 2: raise ValueError("two dry-run evidence items are required")
    if any(not isinstance(item, Mapping) or item.get("within_cap") is not True for item in dry_run):
        raise ValueError("dry-run cost cap must pass for both surfaces")
    canary = evidence.get("canary")
    if not isinstance(canary, Mapping) or canary.get("product_surfaces_complete") is not True:
        raise ValueError("complete two-surface canary evidence is required")
    provenance = evidence.get("provenance")
    if not isinstance(provenance, Mapping) or provenance.get("complete") is not True:
        raise ValueError("complete provenance evidence is required")
    return {
        "schema_version": 1, "state": "canary_ready_for_snapshot", "provider": "weathernext3",
        "location_id": DWD_10416.id, "selected_init_time_utc": evidence.get("selected_init_time_utc"),
        "schema_fingerprint": schema.get("observed_required_fingerprint"), "dry_run_within_cap": True,
        "product_surfaces_complete": True, "provenance_complete": True,
        "production_write_performed": False, "private_fields_exposed": False,
    }


def build_first_snapshot_write_envelope(evidence: Mapping[str, Any]) -> dict[str, object]:
    validated = validate_first_access_evidence(evidence)
    return {
        "schema_version": 1, "state": "first_snapshot_write_eligible", "provider": "weathernext3",
        "location_id": DWD_10416.id, "selected_init_time_utc": validated.get("selected_init_time_utc"),
        "mutation_class": "production_sqlite_forecast_snapshot_write",
        "requires_exact_private_live_data_authority": True,
        "canary_evidence_validated": True, "write_performed": False,
    }


def preflight_access(*, settings: Settings, now: datetime, hours_limit: int, maximum_bytes_billed: int,
                     schema_only: bool = False, adapter: WeatherNextBigQueryAdapter | None = None,
                     job_config_factory: Callable[..., Any] | None = None) -> dict[str, object]:
    _validate_canary_bounds(hours_limit=hours_limit, maximum_bytes_billed=maximum_bytes_billed)
    if not settings.weathernext_cloud_configured:
        return {"schema_version": 1, "state": "access_pending", "coordinates_exposed": False,
                "credentials_exposed": False, "production_write_performed": False}
    assert settings.google_cloud_project and settings.weathernext_bigquery_dataset
    adapter = adapter or WeatherNextBigQueryAdapter(project=settings.google_cloud_project,
                                                     dataset=settings.weathernext_bigquery_dataset)
    try:
        rows = adapter.schema_probe()
    except Exception as exc:
        return {"schema_version": 1, "state": classify_access_error(exc), "coordinates_exposed": False,
                "credentials_exposed": False, "production_write_performed": False}
    schema = schema_summary(rows)
    if schema["state"] != "linked_dataset_ready":
        return {"schema_version": 1, "state": "schema_changed", "schema": schema,
                "coordinates_exposed": False, "credentials_exposed": False,
                "production_write_performed": False}
    if schema_only:
        return {"schema_version": 1, "state": "linked_dataset_ready", "schema": schema,
                "coordinates_exposed": False, "credentials_exposed": False,
                "production_write_performed": False}
    try:
        plan = build_canary_plan(now=now, hours_limit=hours_limit, maximum_bytes_billed=maximum_bytes_billed)
        init_time = datetime.fromisoformat(str(plan["selected_init_time_utc"]).replace("Z", "+00:00"))
        client = adapter._client_or_create()
        dry = dry_run_canary_queries(client=client, project=settings.google_cloud_project,
                                     dataset=settings.weathernext_bigquery_dataset,
                                     lat=DWD_10416.lat, lon=DWD_10416.lon, init_time=init_time,
                                     hours_limit=hours_limit, maximum_bytes_billed=maximum_bytes_billed,
                                     job_config_factory=job_config_factory)
    except WeatherNextCostLimit:
        return {"schema_version": 1, "state": "cost_cap_rejected", "schema": schema,
                "coordinates_exposed": False, "credentials_exposed": False,
                "production_write_performed": False}
    except Exception as exc:
        return {"schema_version": 1, "state": classify_access_error(exc), "schema": schema,
                "coordinates_exposed": False, "credentials_exposed": False,
                "production_write_performed": False}
    return {"schema_version": 1, "state": "ready_for_canary", "schema": schema,
            "plan": plan, "dry_run": [item.as_dict() for item in dry],
            "coordinates_exposed": False, "credentials_exposed": False,
            "production_write_performed": False}


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m rozkalns_weather.weathernext_access")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="build a network-free sanitized WeatherNext first-canary envelope")
    plan.add_argument("--now", required=True, help="UTC timestamp used for dissemination selection")
    plan.add_argument("--init", help="optional explicit UTC init timestamp")
    plan.add_argument("--hours-limit", type=int, default=DEFAULT_CANARY_HOURS)
    plan.add_argument("--max-bytes-billed", type=int, required=True)
    preflight = sub.add_parser("preflight", help="read-only private BigQuery access/schema/dry-run preflight; never writes SQLite")
    preflight.add_argument("--schema-only", action="store_true")
    preflight.add_argument("--hours-limit", type=int, default=DEFAULT_CANARY_HOURS)
    preflight.add_argument("--max-bytes-billed", type=int, required=True)
    validate = sub.add_parser("validate-evidence", help="validate sanitized completed canary evidence from stdin without provider access")
    validate.add_argument("--write-envelope", action="store_true", help="emit only first-snapshot write eligibility; no write is performed")
    args = parser.parse_args()
    if args.command == "plan":
        payload = build_canary_plan(now=_parse_utc(args.now), init_time=_parse_utc(args.init) if args.init else None,
                                    hours_limit=args.hours_limit, maximum_bytes_billed=args.max_bytes_billed)
        print(json.dumps(payload, sort_keys=True, indent=2)); return
    if args.command == "preflight":
        payload = preflight_access(settings=Settings.from_env(), now=datetime.now(timezone.utc),
                                   hours_limit=args.hours_limit, maximum_bytes_billed=args.max_bytes_billed,
                                   schema_only=args.schema_only)
        print(json.dumps(payload, sort_keys=True, indent=2))
        raise SystemExit(0 if payload["state"] in {"linked_dataset_ready", "ready_for_canary"} else 1)
    if args.command == "validate-evidence":
        import sys
        evidence = json.load(sys.stdin)
        if not isinstance(evidence, dict): raise ValueError("first-access evidence must be a JSON object")
        payload = build_first_snapshot_write_envelope(evidence) if args.write_envelope else validate_first_access_evidence(evidence)
        print(json.dumps(payload, sort_keys=True, indent=2)); return


if __name__ == "__main__":
    main()
