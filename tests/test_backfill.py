from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

import pytest

from rozkalns_weather.backfill import BackfillCheckpoint, PublicBackfillRunner, _require_ready_station_database, forecast_integrity, iter_run_times
from rozkalns_weather.db import Database
from rozkalns_weather.locations import DWD_10416
from rozkalns_weather.models import ForecastRun, ForecastValue, Observation
from rozkalns_weather.providers.open_meteo import ICON_D2


def _db(tmp_path: Path) -> Database:
    database = Database(f"sqlite:///{tmp_path / 'backfill.db'}")
    database.initialize()
    database.ensure_location(
        location_id=DWD_10416.id,
        label=DWD_10416.label,
        lat=DWD_10416.lat,
        lon=DWD_10416.lon,
        elevation_m=DWD_10416.elevation_m,
        timezone=DWD_10416.timezone,
    )
    return database


class ForecastStub:
    def __init__(self) -> None:
        self.calls: list[datetime] = []

    def fetch(self, *, lat: float, lon: float, init_time: datetime, availability_time, retrieved_at=None) -> ForecastRun:
        self.calls.append(init_time)
        return ForecastRun(
            provider=ICON_D2.provider_id,
            model_provider=ICON_D2.model_provider,
            model_name=ICON_D2.model_name,
            init_time_utc=init_time,
            retrieved_at_utc=datetime(2026, 9, 7, 12, tzinfo=timezone.utc),
            upstream_available_at_utc=None,
            init_time_quality="single_runs_explicit",
            source_surface="Open-Meteo Single Runs API",
            transport_provider="Open-Meteo",
            values=(
                ForecastValue(
                    valid_time_utc=init_time,
                    lead_hours=0,
                    variable="temperature_2m",
                    value=20.0,
                    unit="degC",
                ),
            ),
            source_metadata={"run_parameter_utc": init_time.strftime("%Y-%m-%dT%H:%M")},
        )


class ObservationStub:
    def __init__(self) -> None:
        self.calls: list[tuple[date, date]] = []

    def fetch_range(self, *, start: date, end: date) -> list[Observation]:
        self.calls.append((start, end))
        return [
            Observation(
                source_provider="DWD",
                station_id="10416",
                location_id=DWD_10416.id,
                observed_at_utc=datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc),
                variable="temperature_2m",
                value=10.0,
                unit="degC",
                source_metadata={"station_identity_pinned": True},
            )
        ]


def test_iter_run_times_requires_explicit_cycle_hours() -> None:
    values = iter_run_times(date(2026, 4, 2), date(2026, 4, 3), (0, 12))
    assert [value.hour for value in values] == [0, 12, 0, 12]
    assert all(value.tzinfo == timezone.utc for value in values)


def test_forecast_backfill_is_checkpoint_resumable_and_idempotent(tmp_path: Path) -> None:
    database = _db(tmp_path)
    stub = ForecastStub()
    runner = PublicBackfillRunner(database, sleep=lambda _: None)
    checkpoint = tmp_path / "icon.json"
    first = runner.forecast_runs(
        model=ICON_D2,
        start=date(2026, 4, 2),
        end=date(2026, 4, 2),
        run_hours=(0, 12),
        checkpoint_path=checkpoint,
        rate_limit_seconds=0,
        adapter=stub,
    )
    second = runner.forecast_runs(
        model=ICON_D2,
        start=date(2026, 4, 2),
        end=date(2026, 4, 2),
        run_hours=(0, 12),
        checkpoint_path=checkpoint,
        rate_limit_seconds=0,
        adapter=stub,
    )
    assert first["processed_runs"] == 2
    assert second["processed_runs"] == 0
    assert len(stub.calls) == 2
    report = forecast_integrity(
        database,
        model=ICON_D2,
        start=date(2026, 4, 2),
        end=date(2026, 4, 2),
        run_hours=(0, 12),
    )
    assert report["ok"] is True
    assert report["missing_runs"] == []


def test_forecast_dry_run_performs_no_fetch_or_write(tmp_path: Path) -> None:
    database = _db(tmp_path)
    stub = ForecastStub()
    result = PublicBackfillRunner(database).forecast_runs(
        model=ICON_D2,
        start=date(2026, 4, 2),
        end=date(2026, 4, 2),
        run_hours=(6,),
        checkpoint_path=tmp_path / "dry.json",
        dry_run=True,
        adapter=stub,
    )
    assert result["state"] == "dry_run"
    assert result["planned_runs"] == ["2026-04-02T06:00:00Z"]
    assert stub.calls == []


def test_truth_backfill_chunks_and_resumes(tmp_path: Path) -> None:
    database = _db(tmp_path)
    stub = ObservationStub()
    runner = PublicBackfillRunner(database, sleep=lambda _: None)
    checkpoint = tmp_path / "truth.json"
    first = runner.observations(
        start=date(2026, 4, 1),
        end=date(2026, 4, 3),
        checkpoint_path=checkpoint,
        chunk_days=2,
        rate_limit_seconds=0,
        adapter=stub,
    )
    second = runner.observations(
        start=date(2026, 4, 1),
        end=date(2026, 4, 3),
        checkpoint_path=checkpoint,
        chunk_days=2,
        rate_limit_seconds=0,
        adapter=stub,
    )
    assert first["inserted_observations"] == 2
    assert second["inserted_observations"] == 0
    assert stub.calls == [(date(2026, 4, 1), date(2026, 4, 2)), (date(2026, 4, 3), date(2026, 4, 3))]


def test_checkpoint_rejects_duplicates_and_skipped_prefix(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(json.dumps({"schema_version": 1, "completed": ["a", "a"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicates"):
        BackfillCheckpoint.load(duplicate)

    reordered = tmp_path / "reordered.json"
    reordered.write_text(json.dumps({"schema_version": 1, "completed": ["b", "a"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="chronological order"):
        BackfillCheckpoint.load(reordered)

    skipped = tmp_path / "skipped.json"
    skipped.write_text(
        json.dumps({"schema_version": 1, "completed": ["2026-04-02T00:00:00Z", "2026-04-02T12:00:00Z"]}),
        encoding="utf-8",
    )
    database = _db(tmp_path)
    with pytest.raises(ValueError, match="exact ordered prefix"):
        PublicBackfillRunner(database).forecast_runs(
            model=ICON_D2,
            start=date(2026, 4, 2),
            end=date(2026, 4, 2),
            run_hours=(0, 6, 12),
            checkpoint_path=skipped,
            dry_run=True,
            adapter=ForecastStub(),
        )


def test_backfill_requires_explicit_preexisting_schema(tmp_path: Path) -> None:
    path = tmp_path / "missing.db"
    database = Database(f"sqlite:///{path}")
    with pytest.raises(RuntimeError, match="explicit `rozkalns-weather init-database`"):
        _require_ready_station_database(database)
    assert not path.exists()
