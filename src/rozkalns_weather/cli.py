from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path

from .backfill import backfill_dwd_truth, coverage_report, deterministic_plan, execute_deterministic_backfill
from .config import Settings
from .db import Database
from .locations import DWD_10416
from .orchestrator import IngestAlreadyRunning, IngestOrchestrator
from .providers.ensemble import ECMWF_AIFS_ENS, ECMWF_IFS_ENS, ICON_D2_EPS, WEATHERNEXT2, OpenMeteoEnsembleAdapter
from .providers.weathernext import WeatherNextBigQueryAdapter
from .reporting import monthly_weather_next_report
from .smoke import smoke_public


def _database(settings: Settings) -> Database:
    database = Database(settings.database_url)
    database.initialize()
    database.ensure_location(location_id=DWD_10416.id, label=DWD_10416.label, lat=DWD_10416.lat, lon=DWD_10416.lon, elevation_m=DWD_10416.elevation_m, timezone=DWD_10416.timezone)
    if settings.home_configured:
        database.ensure_home_location(label=settings.home_label, lat=settings.home_lat, lon=settings.home_lon, timezone=settings.home_timezone)  # type: ignore[arg-type]
    return database


def _print(payload: object) -> None:
    print(json.dumps(payload, sort_keys=True, indent=2, default=str))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_run_hours(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    hours = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not hours or any(hour < 0 or hour > 23 for hour in hours):
        raise ValueError("run hours must be comma-separated UTC hours 0..23")
    return hours


def main() -> None:
    parser = argparse.ArgumentParser(prog="rozkalns-weather")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest-public", help="collect DWD/ICON/ECMWF station benchmark plus home forecasts when configured")
    sub.add_parser("collect-public", help="alias of ingest-public")
    sub.add_parser("ingest-weathernext", help="ingest latest disseminated hourly WeatherNext run for station benchmark and home when configured")
    ensembles = sub.add_parser("ingest-ensembles", help="collect public ICON-D2-EPS/IFS ENS/AIFS ENS member forecasts at station_10416")
    ensembles.add_argument("--include-weathernext2", action="store_true", help="also collect WeatherNext 2 as legacy_ai_context; never substitutes for WN3")
    sub.add_parser("smoke-public", help="optional real-network provider contract smoke checks")
    sub.add_parser("corpus-stats", help="print privacy-safe corpus coverage statistics")
    sub.add_parser("corpus-check", help="run corpus integrity checks")
    diagnose = sub.add_parser("diagnose-weathernext", help="BigQuery access/schema diagnostic without logging credentials or coordinates")
    diagnose.add_argument("--no-point-query", action="store_true", help="schema-only diagnostic")
    report = sub.add_parser("report-monthly", help="generate WeatherNext station-skill monthly report")
    report.add_argument("--month", required=True, help="YYYY-MM")
    backup = sub.add_parser("backup", help="create a consistent SQLite backup at the provided local path")
    backup.add_argument("--output", required=True)

    backfill = sub.add_parser("backfill-public", help="bounded/resumable archived deterministic run backfill at station_10416")
    backfill.add_argument("--provider", required=True, choices=("icon_d2", "ecmwf_ifs", "ecmwf_aifs"))
    backfill.add_argument("--start", required=True, type=_parse_date)
    backfill.add_argument("--end", required=True, type=_parse_date)
    backfill.add_argument("--run-hours", help="optional comma-separated UTC run hours; defaults to provider schedule")
    backfill.add_argument("--checkpoint", required=True, type=Path)
    backfill.add_argument("--rate-limit-seconds", type=float, default=0.0)
    backfill.add_argument("--dry-run", action="store_true")
    backfill.add_argument("--include-noncommon-history", action="store_true", help="allow IFS history before common 2026-04-02 benchmark window")

    truth = sub.add_parser("backfill-truth", help="historical DWD WMO 10416 observation backfill")
    truth.add_argument("--start", required=True, type=_parse_date)
    truth.add_argument("--end", required=True, type=_parse_date)
    truth.add_argument("--dry-run", action="store_true")

    coverage = sub.add_parser("backfill-coverage", help="report expected/stored/missing deterministic runs for a bounded range")
    coverage.add_argument("--provider", required=True, choices=("icon_d2", "ecmwf_ifs", "ecmwf_aifs"))
    coverage.add_argument("--start", required=True, type=_parse_date)
    coverage.add_argument("--end", required=True, type=_parse_date)
    coverage.add_argument("--run-hours")
    coverage.add_argument("--include-noncommon-history", action="store_true")

    args = parser.parse_args()
    settings = Settings.from_env()
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
    if args.command == "ingest-ensembles":
        models = [ICON_D2_EPS, ECMWF_IFS_ENS, ECMWF_AIFS_ENS]
        if args.include_weathernext2:
            models.append(WEATHERNEXT2)
        result: dict[str, object] = {}
        for model in models:
            try:
                run = OpenMeteoEnsembleAdapter(model).fetch(lat=DWD_10416.lat, lon=DWD_10416.lon, retrieved_at=datetime.now(timezone.utc))
                run_id = database.insert_forecast_run(run, location_id=DWD_10416.id)
                result[model.provider_id] = {"state": "ok", "run_id": run_id, "member_count": run.source_metadata.get("member_count"), "init_time_quality": run.init_time_quality}
            except Exception as exc:
                result[model.provider_id] = {"state": "error", "detail": f"{type(exc).__name__}: {exc}"}
        _print({"location_id": DWD_10416.id, "providers": result, "note": "WeatherNext 2 is legacy_ai_context only; WN3 private access is not used."})
        return
    if args.command == "smoke-public":
        _print(smoke_public(settings))
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
    if args.command == "backfill-public":
        plan = deterministic_plan(provider=args.provider, start=args.start, end=args.end, common_window_only=not args.include_noncommon_history, run_hours=_parse_run_hours(args.run_hours))
        _print(execute_deterministic_backfill(database, plan, checkpoint_path=args.checkpoint, dry_run=args.dry_run, rate_limit_seconds=max(0.0, args.rate_limit_seconds)))
        return
    if args.command == "backfill-truth":
        _print(backfill_dwd_truth(database, start=args.start, end=args.end, dry_run=args.dry_run))
        return
    if args.command == "backfill-coverage":
        plan = deterministic_plan(provider=args.provider, start=args.start, end=args.end, common_window_only=not args.include_noncommon_history, run_hours=_parse_run_hours(args.run_hours))
        _print(coverage_report(database, plan))
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
                _print({"state": "ready" if not errors else "schema_changed", "schema_errors": list(errors), "coordinates_exposed": False, "credentials_exposed": False})
                raise SystemExit(0 if not errors else 1)
            except SystemExit:
                raise
            except Exception as exc:
                from .providers.weathernext import classify_bigquery_error
                _print({"state": classify_bigquery_error(exc), "coordinates_exposed": False, "credentials_exposed": False})
                raise SystemExit(1)
        lat = settings.home_lat if settings.home_configured else DWD_10416.lat
        lon = settings.home_lon if settings.home_configured else DWD_10416.lon
        assert lat is not None and lon is not None
        diagnostic = adapter.diagnose(lat=lat, lon=lon, now=datetime.now(timezone.utc))
        _print(diagnostic.as_dict())
        raise SystemExit(0 if diagnostic.state == "ready" else 1)


if __name__ == "__main__":
    main()
