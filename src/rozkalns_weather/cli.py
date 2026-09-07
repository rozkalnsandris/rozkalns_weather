from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json

from .config import Settings
from .db import Database
from .ingest import ingest_public_baselines
from .providers.weathernext import WeatherNextBigQueryAdapter


def main() -> None:
    parser = argparse.ArgumentParser(prog="rozkalns-weather")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest-public", help="ingest DWD/ICON/ECMWF public baselines")
    sub.add_parser("ingest-weathernext", help="ingest the latest available WeatherNext synoptic run")
    args = parser.parse_args()

    settings = Settings.from_env()
    database = Database(settings.database_url)
    database.initialize()
    if settings.home_configured:
        database.ensure_home_location(label=settings.home_label, lat=settings.home_lat, lon=settings.home_lon, timezone=settings.home_timezone)  # type: ignore[arg-type]

    if args.command == "ingest-public":
        print(json.dumps(ingest_public_baselines(settings, database), sort_keys=True))
        return

    if not settings.weathernext_configured:
        database.set_provider_status("weathernext3", state="access_pending", now=datetime.now(timezone.utc), detail="GOOGLE_CLOUD_PROJECT/WEATHERNEXT_BIGQUERY_DATASET or home point missing")
        raise SystemExit("WeatherNext access/config is not ready")

    assert settings.home_lat is not None and settings.home_lon is not None
    assert settings.google_cloud_project and settings.weathernext_bigquery_dataset
    adapter = WeatherNextBigQueryAdapter(project=settings.google_cloud_project, dataset=settings.weathernext_bigquery_dataset)
    try:
        run = adapter.fetch(lat=settings.home_lat, lon=settings.home_lon)
        database.insert_forecast_run(run)
        database.set_provider_status("weathernext3", state="ok", model_name="WeatherNext 3", init_time=run.init_time_utc)
    except Exception as exc:
        database.set_provider_status("weathernext3", state="error", detail=type(exc).__name__)
        raise
