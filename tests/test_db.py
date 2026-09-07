from datetime import datetime, timezone
import sqlite3

import pytest

from rozkalns_weather.db import Database
from rozkalns_weather.models import ForecastRun, ForecastValue


def _run() -> ForecastRun:
    return ForecastRun(
        provider="weathernext3",
        model_provider="Google DeepMind",
        model_name="WeatherNext 3",
        model_version="3.0.0",
        init_time_utc=datetime(2026, 9, 7, 0, tzinfo=timezone.utc),
        retrieved_at_utc=datetime(2026, 9, 7, 8, 15, tzinfo=timezone.utc),
        source_surface="test",
        transport_provider="Google BigQuery",
        source_metadata={"resolution": "0.05deg"},
        values=(
            ForecastValue(
                valid_time_utc=datetime(2026, 9, 7, 9, tzinfo=timezone.utc),
                lead_hours=9,
                variable="temperature_2m",
                statistic="mean",
                value=20.5,
                unit="degC",
            ),
        ),
    )


def _db(tmp_path) -> Database:
    db = Database(f"sqlite:///{tmp_path / 'weather.db'}")
    db.initialize()
    db.ensure_home_location(label="Dortmund-Wickede", lat=51.5, lon=7.6, timezone="Europe/Berlin")
    return db


def test_schema_contains_core_tables(tmp_path) -> None:
    database = _db(tmp_path)
    assert {"locations", "forecast_runs", "forecast_values", "observations", "provider_ingest_status"}.issubset(database.table_names())


def test_forecast_run_is_immutable_and_utc(tmp_path) -> None:
    database = _db(tmp_path)
    run_id = database.insert_forecast_run(_run())
    with database.connect() as connection:
        row = connection.execute("SELECT * FROM forecast_runs WHERE id=?", (run_id,)).fetchone()
        assert row["init_time_utc"].endswith("Z")
        assert row["retrieved_at_utc"].endswith("Z")
        assert row["transport_provider"] == "Google BigQuery"
        assert "0.05deg" in row["source_metadata_json"]
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with database.connect() as connection:
            connection.execute("UPDATE forecast_runs SET status='changed' WHERE id=?", (run_id,))


def test_forecast_value_delete_is_rejected(tmp_path) -> None:
    database = _db(tmp_path)
    run_id = database.insert_forecast_run(_run())
    with database.connect() as connection:
        value_id = connection.execute("SELECT id FROM forecast_values WHERE run_id=?", (run_id,)).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with database.connect() as connection:
            connection.execute("DELETE FROM forecast_values WHERE id=?", (value_id,))
