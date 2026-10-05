from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import Settings
from .db import Database
from .locations import BENCHMARK_LOCATION
from .orchestrator import IngestAlreadyRunning, IngestOrchestrator
from .runtime import database_schema_state, readiness_payload


def _print(payload: object) -> None:
    print(json.dumps(payload, sort_keys=True, indent=2, default=str))


def _ensure_locations(settings: Settings, database: Database) -> None:
    database.ensure_location(
        location_id=BENCHMARK_LOCATION.id,
        label=BENCHMARK_LOCATION.label,
        lat=BENCHMARK_LOCATION.lat,
        lon=BENCHMARK_LOCATION.lon,
        elevation_m=BENCHMARK_LOCATION.elevation_m,
        timezone=BENCHMARK_LOCATION.timezone,
    )
    if settings.home_configured:
        database.ensure_home_location(
            label=settings.home_label,
            lat=settings.home_lat,
            lon=settings.home_lon,
            timezone=settings.home_timezone,
        )


def _database(settings: Settings, *, initialize: bool | None = None, require_ready: bool = True) -> Database:
    database = Database(settings.database_url)
    should_initialize = settings.database_init_mode == "auto" if initialize is None else initialize
    if should_initialize:
        database.initialize()
    state = database_schema_state(database)
    if state["state"] == "ready":
        _ensure_locations(settings, database)
    elif require_ready:
        raise RuntimeError("database schema is not initialized; run 'rozkalns-weather init-database'")
    return database


def main() -> None:
    parser = argparse.ArgumentParser(prog="rozkalns-weather")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-database", help="create the SQLite schema")
    sub.add_parser("readiness", help="print privacy-safe runtime readiness")
    sub.add_parser("ingest-public", help="collect DWD, ICON-D2, ECMWF IFS and ECMWF AIFS")
    sub.add_parser("corpus-stats", help="print corpus statistics")
    sub.add_parser("corpus-check", help="run corpus integrity checks")
    gcs_canary = sub.add_parser("weathernext-gcs-canary", help="run the bounded read-only WeatherNext GCS canary")
    gcs_canary.add_argument("--init", required=True, help="exact UTC init time, for example 2026-10-01T23:00:00Z")
    gcs_persist = sub.add_parser(
        "weathernext-gcs-persist",
        help="persist one validated WeatherNext GCS snapshot into the existing corpus",
    )
    gcs_persist.add_argument("--init", required=True, help="exact UTC init time, for example 2026-10-01T23:00:00Z")
    backup = sub.add_parser("backup", help="create a consistent SQLite backup")
    backup.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.command == "weathernext-gcs-canary":
        from .weathernext_canary import WeatherNextGCSCanaryError, parse_init_utc, run_fixed_canary

        try:
            evidence = run_fixed_canary(parse_init_utc(args.init))
        except WeatherNextGCSCanaryError:
            _print({"state": "gcs_canary_failed"})
            raise SystemExit(1)
        _print(evidence)
        return

    settings = Settings.from_env()

    if args.command == "weathernext-gcs-persist":
        from .weathernext_canary import WeatherNextGCSCanaryError, parse_init_utc
        from .weathernext_persistence import (
            WeatherNextGCSPersistenceError,
            persist_fixed_snapshot,
        )

        database = Database(settings.database_url)
        if database_schema_state(database)["state"] != "ready":
            _print({"state": "weathernext_snapshot_persist_failed"})
            raise SystemExit(1)
        try:
            evidence = persist_fixed_snapshot(
                init_time=parse_init_utc(args.init),
                database=database,
            )
        except (WeatherNextGCSCanaryError, WeatherNextGCSPersistenceError):
            _print({"state": "weathernext_snapshot_persist_failed"})
            raise SystemExit(1)
        _print(evidence)
        return

    if args.command == "init-database":
        database = _database(settings, initialize=True)
        _print({"state": "schema_ready", "runtime_mode": settings.runtime_mode, "home_configured": settings.home_configured})
        return

    if args.command == "readiness":
        database = _database(settings, initialize=False, require_ready=False)
        payload = readiness_payload(settings, database)
        _print(payload)
        raise SystemExit(0 if payload["ready"] else 1)

    database = _database(settings)

    if args.command == "ingest-public":
        try:
            _print(IngestOrchestrator(settings, database).collect_public())
        except IngestAlreadyRunning:
            _print({"state": "already_running"})
            raise SystemExit(2)
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


if __name__ == "__main__":
    main()
