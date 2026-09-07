from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import time as time_module
from typing import Iterable

from .db import Database
from .locations import DWD_10416
from .models import utc_iso
from .providers.dwd_observations import DwdObservationAdapter
from .providers.open_meteo import (
    ECMWF_AIFS,
    ECMWF_IFS,
    ICON_D2,
    OpenMeteoModel,
    OpenMeteoSingleRunAdapter,
)

MODEL_REGISTRY: dict[str, OpenMeteoModel] = {
    ICON_D2.provider_id: ICON_D2,
    ECMWF_IFS.provider_id: ECMWF_IFS,
    ECMWF_AIFS.provider_id: ECMWF_AIFS,
}
ARCHIVE_START = {
    ICON_D2.provider_id: date(2026, 4, 2),
    ECMWF_AIFS.provider_id: date(2026, 4, 2),
    ECMWF_IFS.provider_id: date(2024, 3, 14),
}
COMMON_BENCHMARK_START = date(2026, 4, 2)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_run_hours(value: str) -> tuple[int, ...]:
    hours = tuple(sorted({int(item.strip()) for item in value.split(",") if item.strip()}))
    if not hours or any(hour < 0 or hour > 23 for hour in hours):
        raise ValueError("run hours must be a comma-separated list of UTC hours 0..23")
    return hours


def iter_run_times(start: date, end: date, run_hours: Iterable[int]) -> tuple[datetime, ...]:
    if end < start:
        raise ValueError("end date must not be before start date")
    hours = tuple(sorted(set(run_hours)))
    if not hours or any(hour < 0 or hour > 23 for hour in hours):
        raise ValueError("at least one valid UTC run hour is required")
    output: list[datetime] = []
    cursor = start
    while cursor <= end:
        output.extend(datetime.combine(cursor, time(hour=hour), tzinfo=timezone.utc) for hour in hours)
        cursor += timedelta(days=1)
    return tuple(output)


@dataclass(slots=True)
class BackfillCheckpoint:
    path: Path
    completed: set[str]

    @classmethod
    def load(cls, path: Path) -> "BackfillCheckpoint":
        if not path.exists():
            return cls(path=path, completed=set())
        payload = json.loads(path.read_text(encoding="utf-8"))
        values = payload.get("completed", []) if isinstance(payload, dict) else []
        return cls(path=path, completed={str(value) for value in values})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps({"schema_version": 1, "completed": sorted(self.completed)}, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)


class PublicBackfillRunner:
    def __init__(self, database: Database, *, sleep=time_module.sleep) -> None:
        self.database = database
        self.sleep = sleep

    def forecast_runs(
        self,
        *,
        model: OpenMeteoModel,
        start: date,
        end: date,
        run_hours: Iterable[int],
        checkpoint_path: Path,
        dry_run: bool = False,
        rate_limit_seconds: float = 1.0,
        adapter: OpenMeteoSingleRunAdapter | None = None,
    ) -> dict[str, object]:
        if start < ARCHIVE_START[model.provider_id]:
            raise ValueError(f"{model.provider_id} archive starts at {ARCHIVE_START[model.provider_id].isoformat()}")
        runs = iter_run_times(start, end, run_hours)
        checkpoint = BackfillCheckpoint.load(checkpoint_path)
        adapter = adapter or OpenMeteoSingleRunAdapter(model)
        planned = [run for run in runs if utc_iso(run) not in checkpoint.completed]
        if dry_run:
            return {
                "state": "dry_run",
                "model": model.provider_id,
                "location_id": DWD_10416.id,
                "planned_runs": [utc_iso(run) for run in planned],
                "already_completed": len(runs) - len(planned),
                "common_benchmark": start >= COMMON_BENCHMARK_START,
            }
        inserted = 0
        for index, init_time in enumerate(planned):
            run = adapter.fetch(
                lat=DWD_10416.lat,
                lon=DWD_10416.lon,
                init_time=init_time,
                availability_time=None,
            )
            self.database.insert_forecast_run(run, location_id=DWD_10416.id)
            checkpoint.completed.add(utc_iso(init_time))
            checkpoint.save()
            inserted += 1
            if rate_limit_seconds > 0 and index + 1 < len(planned):
                self.sleep(rate_limit_seconds)
        return {
            "state": "complete",
            "model": model.provider_id,
            "location_id": DWD_10416.id,
            "processed_runs": inserted,
            "checkpoint": str(checkpoint_path),
        }

    def observations(
        self,
        *,
        start: date,
        end: date,
        checkpoint_path: Path,
        dry_run: bool = False,
        chunk_days: int = 14,
        rate_limit_seconds: float = 1.0,
        adapter: DwdObservationAdapter | None = None,
    ) -> dict[str, object]:
        if end < start:
            raise ValueError("end date must not be before start date")
        if chunk_days < 1 or chunk_days > 31:
            raise ValueError("chunk_days must be between 1 and 31")
        checkpoint = BackfillCheckpoint.load(checkpoint_path)
        adapter = adapter or DwdObservationAdapter()
        chunks: list[tuple[date, date]] = []
        cursor = start
        while cursor <= end:
            chunk_end = min(end, cursor + timedelta(days=chunk_days - 1))
            key = f"{cursor.isoformat()}..{chunk_end.isoformat()}"
            if key not in checkpoint.completed:
                chunks.append((cursor, chunk_end))
            cursor = chunk_end + timedelta(days=1)
        if dry_run:
            return {
                "state": "dry_run",
                "station_id": "10416",
                "location_id": DWD_10416.id,
                "planned_chunks": [f"{a.isoformat()}..{b.isoformat()}" for a, b in chunks],
            }
        inserted = 0
        for index, (chunk_start, chunk_end) in enumerate(chunks):
            observations = adapter.fetch_range(start=chunk_start, end=chunk_end)
            inserted += self.database.insert_observations(observations)
            checkpoint.completed.add(f"{chunk_start.isoformat()}..{chunk_end.isoformat()}")
            checkpoint.save()
            if rate_limit_seconds > 0 and index + 1 < len(chunks):
                self.sleep(rate_limit_seconds)
        return {
            "state": "complete",
            "station_id": "10416",
            "location_id": DWD_10416.id,
            "inserted_observations": inserted,
            "checkpoint": str(checkpoint_path),
        }


def forecast_integrity(
    database: Database,
    *,
    model: OpenMeteoModel,
    start: date,
    end: date,
    run_hours: Iterable[int],
) -> dict[str, object]:
    expected = {utc_iso(value) for value in iter_run_times(start, end, run_hours)}
    with database.connect() as connection:
        rows = connection.execute(
            """SELECT init_time_utc, COUNT(*) AS revisions, COUNT(DISTINCT raw_payload_hash) AS payloads
               FROM forecast_runs
               WHERE provider=? AND model_name=? AND location_id=? AND init_time_utc>=? AND init_time_utc<?
               GROUP BY init_time_utc ORDER BY init_time_utc""",
            (
                model.provider_id,
                model.model_name,
                DWD_10416.id,
                f"{start.isoformat()}T00:00:00Z",
                f"{(end + timedelta(days=1)).isoformat()}T00:00:00Z",
            ),
        ).fetchall()
    present = {str(row["init_time_utc"]) for row in rows}
    revisions = {str(row["init_time_utc"]): int(row["revisions"]) for row in rows if int(row["revisions"]) > 1}
    return {
        "ok": not (expected - present),
        "model": model.provider_id,
        "expected_runs": len(expected),
        "present_runs": len(expected & present),
        "missing_runs": sorted(expected - present),
        "unexpected_runs": sorted(present - expected),
        "revised_runs": revisions,
        "immutable_snapshots_preserved": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m rozkalns_weather.backfill")
    parser.add_argument("--database-url", required=True, help="sqlite:/// path; use a non-production corpus unless separately authorized")
    sub = parser.add_subparsers(dest="command", required=True)

    forecast = sub.add_parser("forecast", help="backfill exact Open-Meteo Single Runs")
    forecast.add_argument("--model", choices=sorted(MODEL_REGISTRY), required=True)
    forecast.add_argument("--start", type=_parse_date, required=True)
    forecast.add_argument("--end", type=_parse_date, required=True)
    forecast.add_argument("--run-hours", type=_parse_run_hours, required=True, help="explicit UTC cycle hours, e.g. 0,6,12,18")
    forecast.add_argument("--checkpoint", type=Path, required=True)
    forecast.add_argument("--rate-limit-seconds", type=float, default=1.0)
    forecast.add_argument("--dry-run", action="store_true")

    truth = sub.add_parser("truth", help="backfill pinned DWD WMO 10416 observations through Bright Sky")
    truth.add_argument("--start", type=_parse_date, required=True)
    truth.add_argument("--end", type=_parse_date, required=True)
    truth.add_argument("--checkpoint", type=Path, required=True)
    truth.add_argument("--chunk-days", type=int, default=14)
    truth.add_argument("--rate-limit-seconds", type=float, default=1.0)
    truth.add_argument("--dry-run", action="store_true")

    integrity = sub.add_parser("integrity", help="reconcile expected exact runs against stored immutable snapshots")
    integrity.add_argument("--model", choices=sorted(MODEL_REGISTRY), required=True)
    integrity.add_argument("--start", type=_parse_date, required=True)
    integrity.add_argument("--end", type=_parse_date, required=True)
    integrity.add_argument("--run-hours", type=_parse_run_hours, required=True)

    args = parser.parse_args()
    database = Database(args.database_url)
    database.initialize()
    database.ensure_location(
        location_id=DWD_10416.id,
        label=DWD_10416.label,
        lat=DWD_10416.lat,
        lon=DWD_10416.lon,
        elevation_m=DWD_10416.elevation_m,
        timezone=DWD_10416.timezone,
    )
    runner = PublicBackfillRunner(database)
    if args.command == "forecast":
        result = runner.forecast_runs(
            model=MODEL_REGISTRY[args.model], start=args.start, end=args.end, run_hours=args.run_hours,
            checkpoint_path=args.checkpoint, dry_run=args.dry_run, rate_limit_seconds=args.rate_limit_seconds,
        )
    elif args.command == "truth":
        result = runner.observations(
            start=args.start, end=args.end, checkpoint_path=args.checkpoint, dry_run=args.dry_run,
            chunk_days=args.chunk_days, rate_limit_seconds=args.rate_limit_seconds,
        )
    else:
        result = forecast_integrity(
            database, model=MODEL_REGISTRY[args.model], start=args.start, end=args.end, run_hours=args.run_hours,
        )
    print(json.dumps(result, sort_keys=True, indent=2, default=str))


if __name__ == "__main__":
    main()
