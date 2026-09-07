from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .config import Settings
from .db import Database
from .locations import DWD_10416
from .orchestrator import IngestAlreadyRunning, IngestOrchestrator
from .providers.weathernext import WeatherNextBigQueryAdapter
from .reporting import monthly_weather_next_report
from .runtime import database_schema_state, readiness_payload
from .smoke import smoke_public


def _ensure_locations(settings: Settings, database: Database) -> None:
    database.ensure_location(
        location_id=DWD_10416.id,
        label=DWD_10416.label,
        lat=DWD_10416.lat,
        lon=DWD_10416.lon,
        elevation_m=DWD_10416.elevation_m,
        timezone=DWD_10416.timezone,
    )
    if settings.home_configured:
        database.ensure_home_location(
            label=settings.home_label,
            lat=settings.home_lat,
            lon=settings.home_lon,
            timezone=settings.home_timezone,
        )  # type: ignore[arg-type]


def _database(settings: Settings, *, initialize: bool | None = None, require_ready: bool = True) -> Database:
    database = Database(settings.database_url)
    should_initialize = settings.database_init_mode == "auto" if initialize is None else initialize
    if should_initialize:
        database.initialize()
    state = database_schema_state(database)
    if state["state"] == "ready":
        _ensure_locations(settings, database)
    elif require_ready:
        raise RuntimeError("database schema is not initialized; run `rozkalns-weather init-database` under explicit data-write authority")
    return database


def _print(payload: object) -> None:
    print(json.dumps(payload, sort_keys=True, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(prog="rozkalns-weather")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-database", help="explicitly create/upgrade the SQLite schema; this is a data-write operation")
    sub.add_parser("readiness", help="print privacy-safe runtime readiness without network calls or implicit schema creation")
    sub.add_parser("ingest-public", help="collect DWD/ICON/ECMWF station benchmark plus home forecasts when configured")
    sub.add_parser("collect-public", help="alias of ingest-public")
    sub.add_parser("ingest-weathernext", help="ingest latest disseminated hourly WeatherNext run for station benchmark and home when configured")
    sub.add_parser("smoke-public", help="optional real-network provider contract smoke checks")
    sub.add_parser("corpus-stats", help="print privacy-safe corpus coverage statistics")
    sub.add_parser("corpus-check", help="run corpus integrity checks")
    diagnose = sub.add_parser("diagnose-weathernext", help="BigQuery access/schema diagnostic without logging credentials or coordinates")
    diagnose.add_argument("--no-point-query", action="store_true", help="schema-only diagnostic")
    report = sub.add_parser("report-monthly", help="generate WeatherNext station-skill monthly report")
    report.add_argument("--month", required=True, help="YYYY-MM")
    backup = sub.add_parser("backup", help="create a consistent SQLite backup at the provided local path")
    backup.add_argument("--output", required=True)
    args = parser.parse_args()

    settings = Settings.from_env()

    if args.command == "init-database":
        database = _database(settings, initialize=True)
        _print(
            {
                "state": "schema_ready",
                "runtime_mode": settings.runtime_mode,
                "database_path_exposed": False,
                "home_configured": settings.home_configured,
            }
        )
        return

    if args.command == "readiness":
        database = _database(settings, initialize=False, require_ready=False)
        payload = readiness_payload(settings, database)
        _print(payload)
        raise SystemExit(0 if payload["ready"] else 1)

    if args.command == "smoke-public":
        _print(smoke_public(settings))
        return

    if args.command == "diagnose-weathernext":
        if not settings.weathernext_cloud_configured:
            _print({"state": "access_pending", "coordinates_exposed": False, "credentials_exposed": False})
            raise SystemExit(2)
        assert settings.google_cloud_project and settings.weathernext_bigquery_dataset
        adapter = WeatherNextBigQueryAdapter(project=settings.google_cloud_project, dataset=settings.weathernext_bigquery_dataset)
        if args.no_point_query:
            try:
                from .providers.weathernext import validate_schema_rows

                errors = validate_schema_rows(adapter.schema_probe())
                _print(
                    {
                        "state": "ready" if not errors else "schema_changed",
                        "schema_errors": list(errors),
                        "coordinates_exposed": False,
                        "credentials_exposed": False,
                    }
                )
                raise SystemExit(0 if not errors else 1)
            except SystemExit:
                raise
            except Exception as exc:
                from .providers.weathernext import classify_bigquery_error

                _print(
                    {
                        "state": classify_bigquery_error(exc),
                        "coordinates_exposed": False,
                        "credentials_exposed": False,
                    }
                )
                raise SystemExit(1)
        lat = settings.home_lat if settings.home_configured else DWD_10416.lat
        lon = settings.home_lon if settings.home_configured else DWD_10416.lon
        assert lat is not None and lon is not None
        diagnostic = adapter.diagnose(lat=lat, lon=lon, now=datetime.now(timezone.utc))
        _print(diagnostic.as_dict())
        raise SystemExit(0 if diagnostic.state == "ready" else 1)

    database = _database(settings)
    orchestrator = IngestOrchestrator(settings, database)

    if args.command in {"ingest-public", "collect-public"}:
        try:
            _print(orchestrator.collect_public())
        except IngestAlreadyRunning:
            _print({"state": "already_running"})
            raise SystemExit(2)
        return
    if args.command == "ingest-weathernext":
        _print(orchestrator.collect_weathernext())
        return
    if args.command == "corpus-stats":
        _print(database.corpus_stats())
        return
    if args.command == "corpus-check":
        result = database.corpus_integrity()
        _print(result)
        raise SystemExit(0 if result["ok"] else 1)
    if args.command == "backup":
        database.backup_to(Path(args.output))
        _print({"state": "backup_complete", "output": str(Path(args.output))})
        return
    if args.command == "report-monthly":
        _print(monthly_weather_next_report(database, month=args.month))
        return


if __name__ == "__main__":
    main()
