from __future__ import annotations

import sqlite3

import pytest

from rozkalns_weather.db import Database


def _seed_forecast(database: Database) -> tuple[int, int]:
    database.ensure_home_location(
        label="Dortmund-Wickede",
        lat=51.5,
        lon=7.6,
        timezone="Europe/Berlin",
    )
    with database.connect() as connection:
        run = connection.execute(
            """
            INSERT INTO forecast_runs (
                provider, model_provider, model_name, model_version,
                init_time_utc, retrieved_at_utc, source_surface, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "test",
                "Test Provider",
                "Test Model",
                "v1",
                "2026-09-07T00:00:00Z",
                "2026-09-07T01:00:00Z",
                "test",
                "ok",
            ),
        )
        run_id = int(run.lastrowid)
        value = connection.execute(
            """
            INSERT INTO forecast_values (
                run_id, location_id, valid_time_utc, lead_hours,
                variable, statistic, value, unit
            ) VALUES (?, 'home', ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                "2026-09-07T06:00:00Z",
                6,
                "temperature_2m",
                "mean",
                20.5,
                "degC",
            ),
        )
        value_id = int(value.lastrowid)
    return run_id, value_id


def test_schema_contains_core_tables(tmp_path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'weather.db'}")
    database.initialize()
    assert {
        "locations",
        "forecast_runs",
        "forecast_values",
        "observations",
        "provider_ingest_status",
    }.issubset(database.table_names())


def test_forecast_run_update_is_rejected(tmp_path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'weather.db'}")
    database.initialize()
    run_id, _ = _seed_forecast(database)

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with database.connect() as connection:
            connection.execute(
                "UPDATE forecast_runs SET status='changed' WHERE id=?", (run_id,)
            )


def test_forecast_value_delete_is_rejected(tmp_path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'weather.db'}")
    database.initialize()
    _, value_id = _seed_forecast(database)

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with database.connect() as connection:
            connection.execute("DELETE FROM forecast_values WHERE id=?", (value_id,))
