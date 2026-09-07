from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from .models import ForecastRun, Observation, utc_iso

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
    transport_provider TEXT,
    raw_payload_hash TEXT,
    source_metadata_json TEXT,
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

MIGRATION_COLUMNS = {"forecast_runs": {"transport_provider": "TEXT", "source_metadata_json": "TEXT"}}


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
            for table, columns in MIGRATION_COLUMNS.items():
                existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
                for name, definition in columns.items():
                    if name not in existing:
                        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def ensure_home_location(self, *, label: str, lat: float, lon: float, timezone: str) -> None:
        with self.connect() as connection:
            connection.execute("""
                INSERT INTO locations (id, label, lat, lon, timezone)
                VALUES ('home', ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET label=excluded.label, lat=excluded.lat, lon=excluded.lon, timezone=excluded.timezone
            """, (label, lat, lon, timezone))

    def table_names(self) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {str(row["name"]) for row in rows}

    def insert_forecast_run(self, run: ForecastRun, *, location_id: str = "home") -> int:
        with self.connect() as connection:
            cursor = connection.execute("""
                INSERT INTO forecast_runs (
                    provider, model_provider, model_name, model_version,
                    init_time_utc, retrieved_at_utc, source_surface,
                    transport_provider, raw_payload_hash, source_metadata_json, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (run.provider, run.model_provider, run.model_name, run.model_version, utc_iso(run.init_time_utc), utc_iso(run.retrieved_at_utc), run.source_surface, run.transport_provider, run.raw_payload_hash, json.dumps(run.source_metadata, sort_keys=True), run.status))
            run_id = int(cursor.lastrowid)
            connection.executemany("""
                INSERT INTO forecast_values (
                    run_id, location_id, valid_time_utc, lead_hours, variable,
                    statistic, value, unit, native_value, native_unit,
                    accumulation_window_minutes, quality_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [(run_id, location_id, utc_iso(value.valid_time_utc), value.lead_hours, value.variable, value.statistic, value.value, value.unit, value.native_value, value.native_unit, value.accumulation_window_minutes, value.quality_status) for value in run.values])
            return run_id

    def insert_observations(self, observations: list[Observation]) -> int:
        inserted = 0
        with self.connect() as connection:
            for item in observations:
                cursor = connection.execute("""
                    INSERT OR IGNORE INTO observations (
                        source_provider, station_id, location_id, observed_at_utc,
                        variable, value, unit, quality_status, source_metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (item.source_provider, item.station_id, item.location_id, utc_iso(item.observed_at_utc), item.variable, item.value, item.unit, item.quality_status, json.dumps(item.source_metadata, sort_keys=True)))
                inserted += max(0, cursor.rowcount)
        return inserted

    def set_provider_status(self, provider: str, *, state: str, now: datetime | None = None, detail: str | None = None, model_name: str | None = None, init_time: datetime | None = None) -> None:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        with self.connect() as connection:
            existing = connection.execute("SELECT last_success_at_utc FROM provider_ingest_status WHERE provider=?", (provider,)).fetchone()
            success = utc_iso(now) if state == "ok" else (existing["last_success_at_utc"] if existing else None)
            connection.execute("""
                INSERT INTO provider_ingest_status (
                    provider, model_name, last_attempt_at_utc, last_success_at_utc,
                    last_init_time_utc, state, detail
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    model_name=excluded.model_name,
                    last_attempt_at_utc=excluded.last_attempt_at_utc,
                    last_success_at_utc=excluded.last_success_at_utc,
                    last_init_time_utc=excluded.last_init_time_utc,
                    state=excluded.state,
                    detail=excluded.detail
            """, (provider, model_name, utc_iso(now), success, utc_iso(init_time) if init_time else None, state, detail))

    def provider_statuses(self) -> dict[str, dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM provider_ingest_status ORDER BY provider").fetchall()
        return {row["provider"]: dict(row) for row in rows}

    def latest_hourly(self, *, hours: int = 48, variable: str = "temperature_2m") -> list[dict[str, object]]:
        if not 1 <= hours <= 360:
            raise ValueError("hours must be between 1 and 360")
        with self.connect() as connection:
            rows = connection.execute("""
                WITH latest AS (
                    SELECT provider, MAX(retrieved_at_utc) AS retrieved_at_utc
                    FROM forecast_runs GROUP BY provider
                )
                SELECT r.provider, r.model_name, r.model_version, r.init_time_utc,
                       r.retrieved_at_utc, r.transport_provider, v.valid_time_utc,
                       v.lead_hours, v.variable, v.statistic, v.value, v.unit,
                       v.accumulation_window_minutes
                FROM latest l
                JOIN forecast_runs r ON r.provider=l.provider AND r.retrieved_at_utc=l.retrieved_at_utc
                JOIN forecast_values v ON v.run_id=r.id
                WHERE v.variable=? AND v.lead_hours <= ?
                ORDER BY v.valid_time_utc, r.provider, v.statistic
            """, (variable, hours)).fetchall()
        return [dict(row) for row in rows]

    def temperature_verification_pairs(self, *, days: int = 90) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute("""
                WITH forecast AS (
                    SELECT r.provider, r.model_version, v.valid_time_utc, v.lead_hours,
                           v.value AS forecast_value,
                           MAX(CASE WHEN v.statistic='p10' THEN v.value END) OVER (PARTITION BY r.id, v.valid_time_utc, v.variable) AS p10,
                           MAX(CASE WHEN v.statistic='p90' THEN v.value END) OVER (PARTITION BY r.id, v.valid_time_utc, v.variable) AS p90,
                           v.statistic
                    FROM forecast_runs r
                    JOIN forecast_values v ON v.run_id=r.id
                    WHERE v.variable='temperature_2m'
                      AND v.statistic IN ('deterministic','mean','p50','p10','p90')
                      AND julianday(v.valid_time_utc) >= julianday('now', ?)
                )
                SELECT f.provider, f.model_version, f.valid_time_utc, f.lead_hours,
                       f.forecast_value, f.p10, f.p90, o.value AS observed_value
                FROM forecast f
                JOIN observations o ON o.variable='temperature_2m' AND o.observed_at_utc=f.valid_time_utc
                WHERE f.statistic IN ('deterministic','mean')
                ORDER BY f.provider, f.valid_time_utc
            """, (f"-{days} days",)).fetchall()
        return [dict(row) for row in rows]
