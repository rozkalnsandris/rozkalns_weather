from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS locations (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    lat REAL NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lon REAL NOT NULL CHECK (lon BETWEEN -180 AND 180),
    elevation_m REAL,
    timezone TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecast_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model_provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT,
    init_time_utc TEXT NOT NULL,
    retrieved_at_utc TEXT NOT NULL,
    source_surface TEXT NOT NULL,
    raw_payload_hash TEXT,
    status TEXT NOT NULL DEFAULT 'ok',
    UNIQUE(provider, model_name, init_time_utc, retrieved_at_utc)
);

CREATE TABLE IF NOT EXISTS forecast_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES forecast_runs(id),
    location_id TEXT NOT NULL REFERENCES locations(id),
    valid_time_utc TEXT NOT NULL,
    lead_hours REAL NOT NULL CHECK (lead_hours >= 0),
    variable TEXT NOT NULL,
    statistic TEXT NOT NULL DEFAULT 'deterministic',
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    native_value REAL,
    native_unit TEXT,
    accumulation_window_minutes INTEGER,
    quality_status TEXT,
    UNIQUE(run_id, location_id, valid_time_utc, variable, statistic, accumulation_window_minutes)
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_provider TEXT NOT NULL,
    station_id TEXT,
    location_id TEXT,
    observed_at_utc TEXT NOT NULL,
    variable TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    quality_status TEXT,
    source_metadata_json TEXT,
    UNIQUE(source_provider, station_id, observed_at_utc, variable)
);

CREATE TABLE IF NOT EXISTS provider_ingest_status (
    provider TEXT PRIMARY KEY,
    model_name TEXT,
    last_attempt_at_utc TEXT,
    last_success_at_utc TEXT,
    last_init_time_utc TEXT,
    state TEXT NOT NULL,
    detail TEXT
);

CREATE TRIGGER IF NOT EXISTS forecast_runs_no_update
BEFORE UPDATE ON forecast_runs
BEGIN
    SELECT RAISE(ABORT, 'forecast_runs are immutable');
END;

CREATE TRIGGER IF NOT EXISTS forecast_runs_no_delete
BEFORE DELETE ON forecast_runs
BEGIN
    SELECT RAISE(ABORT, 'forecast_runs are immutable');
END;

CREATE TRIGGER IF NOT EXISTS forecast_values_no_update
BEFORE UPDATE ON forecast_values
BEGIN
    SELECT RAISE(ABORT, 'forecast_values are immutable');
END;

CREATE TRIGGER IF NOT EXISTS forecast_values_no_delete
BEFORE DELETE ON forecast_values
BEGIN
    SELECT RAISE(ABORT, 'forecast_values are immutable');
END;
"""


class Database:
    def __init__(self, database_url: str) -> None:
        prefix = "sqlite:///"
        if not database_url.startswith(prefix):
            raise ValueError("Only sqlite:/// DATABASE_URL values are supported in the MVP")
        self.path = database_url[len(prefix) :]
        if not self.path:
            raise ValueError("DATABASE_URL must include a SQLite path")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA_SQL)

    def ensure_home_location(
        self,
        *,
        label: str,
        lat: float,
        lon: float,
        timezone: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO locations (id, label, lat, lon, timezone)
                VALUES ('home', ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    label = excluded.label,
                    lat = excluded.lat,
                    lon = excluded.lon,
                    timezone = excluded.timezone
                """,
                (label, lat, lon, timezone),
            )

    def table_names(self) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        return {str(row["name"]) for row in rows}
