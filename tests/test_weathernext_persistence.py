from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from rozkalns_weather import weathernext_persistence


INIT = datetime(2026, 10, 4, 6, tzinfo=timezone.utc)


class _Database:
    def __init__(self, lock_path: Path) -> None:
        self.calls = []
        self.lock_path = lock_path

    def insert_forecast_run(self, run, *, location_id: str) -> int:
        self.calls.append((run, location_id))
        return 17


def _result():
    run = SimpleNamespace(
        provider="weathernext3",
        model_version="3.0.0",
        init_time_utc=INIT,
        values=tuple(range(216)),
    )
    evidence = {
        "selected_init_time_utc": "2026-10-04T06:00:00Z",
        "lead_count": 6,
        "materialized_scalar_count": 288,
        "schema_valid": True,
        "provenance_complete": True,
        "automatic_retry_used": False,
        "full_dataset_load_used": False,
        "full_ensemble_fallback_used": False,
    }
    return SimpleNamespace(run=run, evidence=evidence)


def test_persist_fixed_snapshot_writes_only_station_forecast_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database = _Database(tmp_path / "weather.db.ingest.lock")
    result = _result()
    monkeypatch.setattr(
        weathernext_persistence,
        "read_fixed_snapshot",
        lambda init_time: result,
    )

    observed = weathernext_persistence.persist_fixed_snapshot(
        init_time=INIT,
        database=database,
    )

    assert database.calls == [(result.run, "station_05480")]
    assert not database.lock_path.exists()
    assert observed == {
        "state": "weathernext_snapshot_persisted",
        "provider": "weathernext3",
        "model_version": "3.0.0",
        "location_id": "station_05480",
        "selected_init_time_utc": "2026-10-04T06:00:00Z",
        "lead_count": 6,
        "source_materialized_scalar_count": 288,
        "persisted_value_count": 216,
        "schema_valid": True,
        "provenance_complete": True,
        "automatic_retry_used": False,
        "full_dataset_load_used": False,
        "full_ensemble_fallback_used": False,
        "raw_values_exposed": False,
        "coordinates_exposed": False,
        "production_write_performed": True,
    }


def test_persist_fixed_snapshot_fails_before_write_on_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database = _Database(tmp_path / "weather.db.ingest.lock")
    result = _result()
    result.run.provider = "unexpected"
    monkeypatch.setattr(
        weathernext_persistence,
        "read_fixed_snapshot",
        lambda init_time: result,
    )

    with pytest.raises(
        weathernext_persistence.WeatherNextGCSPersistenceError,
        match="identity failed closed",
    ):
        weathernext_persistence.persist_fixed_snapshot(
            init_time=INIT,
            database=database,
        )

    assert database.calls == []


def test_persist_fixed_snapshot_wraps_database_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class _FailingDatabase:
        lock_path = tmp_path / "weather.db.ingest.lock"

        def insert_forecast_run(self, run, *, location_id: str) -> int:
            raise RuntimeError("fixture")

    monkeypatch.setattr(
        weathernext_persistence,
        "read_fixed_snapshot",
        lambda init_time: _result(),
    )

    with pytest.raises(
        weathernext_persistence.WeatherNextGCSPersistenceError,
        match="persistence failed closed",
    ):
        weathernext_persistence.persist_fixed_snapshot(
            init_time=INIT,
            database=_FailingDatabase(),
        )

    assert not _FailingDatabase.lock_path.exists()


def test_persist_fixed_snapshot_fails_closed_when_public_ingest_lock_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database = _Database(tmp_path / "weather.db.ingest.lock")
    database.lock_path.write_text("busy", encoding="utf-8")
    monkeypatch.setattr(
        weathernext_persistence,
        "read_fixed_snapshot",
        lambda init_time: _result(),
    )

    with pytest.raises(
        weathernext_persistence.WeatherNextGCSPersistenceError,
        match="persistence failed closed",
    ) as exc_info:
        weathernext_persistence.persist_fixed_snapshot(
            init_time=INIT,
            database=database,
        )

    assert type(exc_info.value.__cause__).__name__ == "IngestAlreadyRunning"
    assert database.calls == []
    assert database.lock_path.exists()
