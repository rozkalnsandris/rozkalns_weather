from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import time
from typing import Callable, Iterable

from .db import Database
from .locations import DWD_10416
from .providers.dwd_observations import DwdObservationAdapter
from .providers.open_meteo import ECMWF_AIFS, ECMWF_IFS, ICON_D2, OpenMeteoModel, OpenMeteoSingleRunAdapter

COMMON_ARCHIVE_START = date(2026, 4, 2)
IFS_ARCHIVE_START = date(2024, 3, 14)
ARCHIVE_STARTS = {"icon_d2": COMMON_ARCHIVE_START, "ecmwf_aifs": COMMON_ARCHIVE_START, "ecmwf_ifs": IFS_ARCHIVE_START}
MODELS: dict[str, OpenMeteoModel] = {"icon_d2": ICON_D2, "ecmwf_ifs": ECMWF_IFS, "ecmwf_aifs": ECMWF_AIFS}
RUN_HOURS = {"icon_d2": (0, 3, 6, 9, 12, 15, 18, 21), "ecmwf_ifs": (0, 6, 12, 18), "ecmwf_aifs": (0, 6, 12, 18)}


@dataclass(frozen=True, slots=True)
class BackfillPlan:
    provider: str
    start: date
    end: date
    run_hours: tuple[int, ...]
    common_window_only: bool = True

    def __post_init__(self) -> None:
        if self.provider not in MODELS:
            raise ValueError(f"unsupported deterministic backfill provider: {self.provider}")
        if self.end < self.start:
            raise ValueError("end must not precede start")
        floor = COMMON_ARCHIVE_START if self.common_window_only else ARCHIVE_STARTS[self.provider]
        if self.start < floor:
            raise ValueError(f"{self.provider} archive starts at {floor.isoformat()} for this mode")
        if not self.run_hours or any(hour < 0 or hour > 23 for hour in self.run_hours):
            raise ValueError("run_hours must contain UTC hours 0..23")

    def runs(self) -> tuple[datetime, ...]:
        result: list[datetime] = []
        current = self.start
        while current <= self.end:
            result.extend(datetime(current.year, current.month, current.day, hour, tzinfo=timezone.utc) for hour in self.run_hours)
            current += timedelta(days=1)
        return tuple(result)


@dataclass(slots=True)
class BackfillCheckpoint:
    provider: str
    completed_runs: list[str]
    failed_runs: dict[str, str]

    @classmethod
    def load(cls, path: Path, *, provider: str) -> "BackfillCheckpoint":
        if not path.exists():
            return cls(provider=provider, completed_runs=[], failed_runs={})
        payload = json.loads(path.read_text())
        if payload.get("provider") != provider:
            raise ValueError("checkpoint provider does not match plan")
        return cls(provider=provider, completed_runs=list(payload.get("completed_runs", [])), failed_runs=dict(payload.get("failed_runs", {})))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n")


def deterministic_plan(*, provider: str, start: date, end: date, common_window_only: bool = True, run_hours: Iterable[int] | None = None) -> BackfillPlan:
    return BackfillPlan(provider=provider, start=start, end=end, run_hours=tuple(run_hours or RUN_HOURS[provider]), common_window_only=common_window_only)


def execute_deterministic_backfill(
    database: Database,
    plan: BackfillPlan,
    *,
    checkpoint_path: Path,
    dry_run: bool = False,
    rate_limit_seconds: float = 0.0,
    adapter_factory: Callable[[OpenMeteoModel], OpenMeteoSingleRunAdapter] = OpenMeteoSingleRunAdapter,
) -> dict[str, object]:
    checkpoint = BackfillCheckpoint.load(checkpoint_path, provider=plan.provider)
    complete = set(checkpoint.completed_runs)
    model = MODELS[plan.provider]
    adapter = adapter_factory(model)
    expected = plan.runs()
    attempted = inserted = skipped = failed = 0
    for init in expected:
        key = init.isoformat().replace("+00:00", "Z")
        if key in complete:
            skipped += 1
            continue
        if dry_run:
            continue
        attempted += 1
        try:
            run = adapter.fetch(lat=DWD_10416.lat, lon=DWD_10416.lon, init_time=init, availability_time=init, retrieved_at=datetime.now(timezone.utc))
            metadata = dict(run.source_metadata)
            metadata.update({"backfill": True, "historical_availability_time_quality": "not_exposed_by_single_runs_archive", "comparison_location": DWD_10416.id})
            run = replace(run, upstream_available_at_utc=None, source_metadata=metadata)
            database.insert_forecast_run(run, location_id=DWD_10416.id)
            checkpoint.completed_runs.append(key)
            checkpoint.failed_runs.pop(key, None)
            checkpoint.save(checkpoint_path)
            inserted += 1
        except Exception as exc:
            checkpoint.failed_runs[key] = f"{type(exc).__name__}: {exc}"
            checkpoint.save(checkpoint_path)
            failed += 1
        if rate_limit_seconds > 0:
            time.sleep(rate_limit_seconds)
    return {"provider": plan.provider, "dry_run": dry_run, "expected_runs": len(expected), "attempted": attempted, "inserted_or_idempotent": inserted, "checkpoint_skipped": skipped, "failed": failed, "remaining": len(expected) - len(set(checkpoint.completed_runs)), "location_id": DWD_10416.id, "common_window_only": plan.common_window_only}


def backfill_dwd_truth(database: Database, *, start: date, end: date, adapter: DwdObservationAdapter | None = None, dry_run: bool = False) -> dict[str, object]:
    if end < start:
        raise ValueError("end must not precede start")
    adapter = adapter or DwdObservationAdapter()
    if dry_run:
        return {"dry_run": True, "start": start.isoformat(), "end": end.isoformat(), "station_id": "10416", "location_id": DWD_10416.id}
    observations = adapter.fetch_range(start=start, end=end)
    if any(item.station_id != "10416" or item.location_id != DWD_10416.id for item in observations):
        raise ValueError("historical truth adapter returned a station/location drift")
    inserted = database.insert_observations(observations)
    return {"dry_run": False, "start": start.isoformat(), "end": end.isoformat(), "station_id": "10416", "location_id": DWD_10416.id, "observations_returned": len(observations), "inserted": inserted}


def coverage_report(database: Database, plan: BackfillPlan) -> dict[str, object]:
    expected = {item.isoformat().replace("+00:00", "Z") for item in plan.runs()}
    with database.connect() as connection:
        rows = connection.execute("""SELECT DISTINCT init_time_utc FROM forecast_runs WHERE provider=? AND location_id=? AND init_time_utc>=? AND init_time_utc<?""", (plan.provider, DWD_10416.id, f"{plan.start.isoformat()}T00:00:00Z", f"{(plan.end + timedelta(days=1)).isoformat()}T00:00:00Z")).fetchall()
    stored = {str(row["init_time_utc"]) for row in rows}
    missing = sorted(expected - stored)
    return {"provider": plan.provider, "expected_runs": len(expected), "stored_runs": len(expected & stored), "missing_runs": missing, "complete": not missing}
