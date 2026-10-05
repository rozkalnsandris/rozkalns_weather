from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from rozkalns_weather import weathernext_persistence


INIT = datetime(2026, 10, 4, 6, tzinfo=timezone.utc)


class _Database:
    def __init__(self) -> None:
        self.calls = []

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
) -> None:
    database = _Database()
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
) -> None:
    database = _Database()
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
) -> None:
    class _FailingDatabase:
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
