from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys

from .config import Settings
from .db import Database
from .locations import DWD_10416
from .orchestrator import IngestAlreadyRunning, IngestOrchestrator
from .providers.weathernext import WeatherNextBigQueryAdapter
from .reporting import monthly_weather_next_report
from .rollout import RECOVERY_DECISIONS, build_rollout_plan, validate_post_rollout_evidence
from .rollout_live_preflight import evaluate_first_public_rollout_preflight
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


def _invalid_rollout(exc: Exception) -> None:
    _print(
        {
            "schema_version": 1,
            "state": "invalid",
            "error": str(exc),
            "live_authority_granted": False,
            "production_data_authority_granted": False,
            "privacy": {
                "coordinates_exposed": False,
                "credentials_exposed": False,
                "database_path_exposed": False,
                "host_private_paths_exposed": False,
                "raw_logs_exposed": False,
            },
        }
    )


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
    preflight = sub.add_parser(
        "rollout-preflight",
        help="validate the fixed public-only source package and emit a sanitized later-LIVE rollout envelope without network/runtime mutation",
    )
    preflight.add_argument("--source-sha", required=True, help="exact reviewed 40-character weather commit SHA")
    preflight.add_argument("--start", required=True, help="bounded bootstrap start date YYYY-MM-DD")
    preflight.add_argument("--end", required=True, help="bounded bootstrap end date YYYY-MM-DD")
    preflight.add_argument("--models", required=True, help="exact comma-separated bootstrap models")
    preflight.add_argument("--run-hours", required=True, help="exact comma-separated UTC run hours")
    preflight.add_argument("--recovery-decision", required=True, choices=RECOVERY_DECISIONS)
    preflight.add_argument(
        "--completed-stage",
        action="append",
        default=[],
        help="repeat only for an already checkpointed ordered stage prefix; stage skipping is rejected",
    )
    sub.add_parser(
        "rollout-evidence-validate",
        help="read a privacy-safe post-rollout evidence JSON object from stdin and validate public-only pass/fail postconditions",
    )
    sub.add_parser(
        "rollout-live-preflight-validate",
        help="read sanitized JIT evidence from stdin and emit PASS/BLOCKED for the later first public rollout without creating or consuming LIVE authority",
    )
    diagnose = sub.add_parser("diagnose-weathernext", help="BigQuery access/schema diagnostic without logging credentials or coordinates")
    diagnose.add_argument("--no-point-query", action="store_true", help="schema-only diagnostic")
    report = sub.add_parser("report-monthly", help="generate WeatherNext station-skill monthly report")
    report.add_argument("--month", required=True, help="YYYY-MM")
    backup = sub.add_parser("backup", help="create a consistent SQLite backup at the provided local path")
    backup.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.command == "rollout-preflight":
        try:
            payload = build_rollout_plan(
                source_sha=args.source_sha,
                start=date.fromisoformat(args.start),
                end=date.fromisoformat(args.end),
                models=args.models,
                run_hours_utc=args.run_hours,
                recovery_decision=args.recovery_decision,
                completed_stages=args.completed_stage,
            )
        except (ValueError, json.JSONDecodeError) as exc:
            _invalid_rollout(exc)
            raise SystemExit(2)
        _print(payload)
        return

    if args.command == "rollout-evidence-validate":
        try:
            evidence = json.load(sys.stdin)
            if not isinstance(evidence, dict):
                raise ValueError("rollout evidence must be a JSON object")
            payload = validate_post_rollout_evidence(evidence)
        except (ValueError, json.JSONDecodeError) as exc:
            _invalid_rollout(exc)
            raise SystemExit(2)
        _print(payload)
        return

    if args.command == "rollout-live-preflight-validate":
        try:
            evidence = json.load(sys.stdin)
            if not isinstance(evidence, dict):
                raise ValueError("rollout live preflight evidence must be a JSON object")
            payload = evaluate_first_public_rollout_preflight(evidence)
        except (ValueError, json.JSONDecodeError) as exc:
            _invalid_rollout(exc)
            raise SystemExit(2)
        _print(payload)
        if payload["state"] == "BLOCKED":
            raise SystemExit(3)
        return

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
