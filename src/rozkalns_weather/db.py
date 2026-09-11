from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Iterable, Iterator

from .models import ForecastRun, Observation, utc_iso
from .semantics import VARIABLES, validate_semantics

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
    location_id TEXT NOT NULL REFERENCES locations(id),
    init_time_utc TEXT NOT NULL,
    retrieved_at_utc TEXT NOT NULL,
    upstream_available_at_utc TEXT,
    init_time_quality TEXT NOT NULL DEFAULT 'unknown',
    source_surface TEXT NOT NULL,
    transport_provider TEXT,
    raw_payload_hash TEXT,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    source_metadata_json TEXT,
    status TEXT NOT NULL DEFAULT 'ok',
    UNIQUE(provider, model_name, location_id, init_time_utc, retrieved_at_utc)
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
CREATE TABLE IF NOT EXISTS model_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model_version TEXT,
    effective_at_utc TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_url TEXT,
    note TEXT,
    UNIQUE(provider, effective_at_utc, event_type, model_version)
);
CREATE INDEX IF NOT EXISTS idx_forecast_identity ON forecast_runs(provider, model_name, location_id, init_time_utc, raw_payload_hash);
CREATE INDEX IF NOT EXISTS idx_forecast_values_valid ON forecast_values(location_id, valid_time_utc, variable);
CREATE INDEX IF NOT EXISTS idx_observations_valid ON observations(location_id, observed_at_utc, variable);
CREATE TRIGGER IF NOT EXISTS forecast_runs_no_update BEFORE UPDATE ON forecast_runs BEGIN SELECT RAISE(ABORT, 'forecast_runs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS forecast_runs_no_delete BEFORE DELETE ON forecast_runs BEGIN SELECT RAISE(ABORT, 'forecast_runs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS forecast_values_no_update BEFORE UPDATE ON forecast_values BEGIN SELECT RAISE(ABORT, 'forecast_values are immutable'); END;
CREATE TRIGGER IF NOT EXISTS forecast_values_no_delete BEFORE DELETE ON forecast_values BEGIN SELECT RAISE(ABORT, 'forecast_values are immutable'); END;
"""

# Source has not been deployed live yet. These additive columns keep developer DBs
# readable; the first live corpus is required to start from the current schema so
# the location-aware uniqueness constraint is present from day one.
MIGRATION_COLUMNS = {
    "forecast_runs": {
        "transport_provider": "TEXT",
        "source_metadata_json": "TEXT",
        "upstream_available_at_utc": "TEXT",
        "init_time_quality": "TEXT NOT NULL DEFAULT 'unknown'",
        "revision": "INTEGER NOT NULL DEFAULT 1",
        "location_id": "TEXT",
    }
}


def _canonical_run_hash(run: ForecastRun) -> str:
    values = [
        {
            "valid": utc_iso(v.valid_time_utc),
            "lead": round(v.lead_hours, 6),
            "variable": v.variable,
            "statistic": v.statistic,
            "value": round(v.value, 10),
            "unit": v.unit,
            "window": v.accumulation_window_minutes,
        }
        for v in run.values
    ]
    values.sort(key=lambda x: (x["valid"], x["variable"], x["statistic"], x["window"] or -1))
    payload = {
        "provider": run.provider,
        "model_name": run.model_name,
        "model_version": run.model_version,
        "init_time_utc": utc_iso(run.init_time_utc),
        "values": values,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Database:
    def __init__(self, database_url: str) -> None:
        prefix = "sqlite:///"
        if not database_url.startswith(prefix):
            raise ValueError("Only sqlite:/// DATABASE_URL values are supported")
        self.path = database_url[len(prefix):]
        if not self.path:
            raise ValueError("DATABASE_URL must include a SQLite path")

    @property
    def lock_path(self) -> Path:
        return Path("/tmp/rozkalns-weather-memory.ingest.lock") if self.path == ":memory:" else Path(self.path + ".ingest.lock")

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
            connection.execute("CREATE INDEX IF NOT EXISTS idx_forecast_identity ON forecast_runs(provider, model_name, location_id, init_time_utc, raw_payload_hash)")

    def ensure_location(self, *, location_id: str, label: str, lat: float, lon: float, timezone: str, elevation_m: float | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO locations (id,label,lat,lon,elevation_m,timezone)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET label=excluded.label,lat=excluded.lat,lon=excluded.lon,elevation_m=excluded.elevation_m,timezone=excluded.timezone""",
                (location_id, label, lat, lon, elevation_m, timezone),
            )

    def ensure_home_location(self, *, label: str, lat: float, lon: float, timezone: str) -> None:
        self.ensure_location(location_id="home", label=label, lat=lat, lon=lon, timezone=timezone)

    def table_names(self) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {str(row["name"]) for row in rows}

    def insert_forecast_run(self, run: ForecastRun, *, location_id: str = "home") -> int:
        content_hash = run.raw_payload_hash or _canonical_run_hash(run)
        init_iso = utc_iso(run.init_time_utc)
        with self.connect() as connection:
            existing = connection.execute(
                """SELECT id FROM forecast_runs
                   WHERE provider=? AND model_name=? AND location_id=? AND init_time_utc=? AND raw_payload_hash=?
                   ORDER BY revision DESC LIMIT 1""",
                (run.provider, run.model_name, location_id, init_iso, content_hash),
            ).fetchone()
            if existing:
                return int(existing["id"])
            revision = int(connection.execute(
                """SELECT COALESCE(MAX(revision),0)+1 AS next_revision FROM forecast_runs
                   WHERE provider=? AND model_name=? AND location_id=? AND init_time_utc=?""",
                (run.provider, run.model_name, location_id, init_iso),
            ).fetchone()["next_revision"])
            cursor = connection.execute(
                """INSERT INTO forecast_runs (
                    provider,model_provider,model_name,model_version,location_id,init_time_utc,retrieved_at_utc,
                    upstream_available_at_utc,init_time_quality,source_surface,transport_provider,raw_payload_hash,
                    revision,source_metadata_json,status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run.provider, run.model_provider, run.model_name, run.model_version, location_id, init_iso,
                    utc_iso(run.retrieved_at_utc), utc_iso(run.upstream_available_at_utc) if run.upstream_available_at_utc else None,
                    run.init_time_quality, run.source_surface, run.transport_provider, content_hash, revision,
                    json.dumps(run.source_metadata, sort_keys=True), run.status,
                ),
            )
            run_id = int(cursor.lastrowid)
            connection.executemany(
                """INSERT INTO forecast_values (
                    run_id,location_id,valid_time_utc,lead_hours,variable,statistic,value,unit,native_value,native_unit,
                    accumulation_window_minutes,quality_status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (run_id, location_id, utc_iso(v.valid_time_utc), v.lead_hours, v.variable, v.statistic, v.value, v.unit,
                     v.native_value, v.native_unit, v.accumulation_window_minutes, v.quality_status)
                    for v in run.values
                ],
            )
            return run_id

    def insert_observations(self, observations: list[Observation]) -> int:
        inserted = 0
        with self.connect() as connection:
            for item in observations:
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO observations (
                       source_provider,station_id,location_id,observed_at_utc,variable,value,unit,quality_status,source_metadata_json
                       ) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (item.source_provider, item.station_id, item.location_id, utc_iso(item.observed_at_utc), item.variable,
                     item.value, item.unit, item.quality_status, json.dumps(item.source_metadata, sort_keys=True)),
                )
                inserted += max(0, cursor.rowcount)
        return inserted

    def set_provider_status(self, provider: str, *, state: str, now: datetime | None = None, detail: str | None = None, model_name: str | None = None, init_time: datetime | None = None) -> None:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        with self.connect() as connection:
            existing = connection.execute("SELECT * FROM provider_ingest_status WHERE provider=?", (provider,)).fetchone()
            success = utc_iso(now) if state in {"ok", "partial"} else (existing["last_success_at_utc"] if existing else None)
            last_init = utc_iso(init_time) if init_time else (existing["last_init_time_utc"] if existing else None)
            saved_model = model_name or (existing["model_name"] if existing else None)
            connection.execute(
                """INSERT INTO provider_ingest_status (provider,model_name,last_attempt_at_utc,last_success_at_utc,last_init_time_utc,state,detail)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(provider) DO UPDATE SET model_name=excluded.model_name,last_attempt_at_utc=excluded.last_attempt_at_utc,
                   last_success_at_utc=excluded.last_success_at_utc,last_init_time_utc=excluded.last_init_time_utc,state=excluded.state,detail=excluded.detail""",
                (provider, saved_model, utc_iso(now), success, last_init, state, detail),
            )

    def provider_statuses(self) -> dict[str, dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM provider_ingest_status ORDER BY provider").fetchall()
        return {str(row["provider"]): dict(row) for row in rows}

    def provider_freshness_evidence(self, *, location_id: str = "station_10416") -> dict[str, dict[str, object]]:
        with self.connect() as connection:
            forecast_rows = connection.execute(
                """WITH latest AS (
                    SELECT provider,MAX(retrieved_at_utc) AS retrieved_at_utc FROM forecast_runs
                    WHERE location_id=? GROUP BY provider
                ) SELECT r.provider,r.init_time_utc,r.retrieved_at_utc,MAX(v.valid_time_utc) AS latest_valid_time_utc
                  FROM latest l JOIN forecast_runs r ON r.provider=l.provider AND r.retrieved_at_utc=l.retrieved_at_utc
                  JOIN forecast_values v ON v.run_id=r.id
                  WHERE r.location_id=? GROUP BY r.id,r.provider,r.init_time_utc,r.retrieved_at_utc
                  ORDER BY r.provider""",
                (location_id, location_id),
            ).fetchall()
            observation = connection.execute(
                """SELECT MAX(observed_at_utc) AS last_observed_at_utc FROM observations
                   WHERE source_provider='DWD' AND location_id=?""",
                (location_id,),
            ).fetchone()
        result = {
            str(row["provider"]): {
                "last_init_time_utc": row["init_time_utc"],
                "last_retrieved_at_utc": row["retrieved_at_utc"],
                "latest_valid_time_utc": row["latest_valid_time_utc"],
            }
            for row in forecast_rows
        }
        if observation and observation["last_observed_at_utc"]:
            result["dwd_observations"] = {"last_observed_at_utc": observation["last_observed_at_utc"]}
        return result

    def latest_observations(self, *, location_id: str = "station_10416") -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """WITH latest AS (
                    SELECT variable,MAX(observed_at_utc) AS observed_at_utc FROM observations
                    WHERE source_provider='DWD' AND location_id=? GROUP BY variable
                ) SELECT o.variable,o.value,o.unit,o.observed_at_utc,o.source_provider,o.station_id,o.location_id,o.quality_status
                  FROM latest l JOIN observations o ON o.variable=l.variable AND o.observed_at_utc=l.observed_at_utc
                  WHERE o.source_provider='DWD' AND o.location_id=? ORDER BY o.variable""",
                (location_id, location_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_hourly(self, *, hours: int = 48, variable: str = "temperature_2m", location_id: str = "home") -> list[dict[str, object]]:
        if not 1 <= hours <= 360:
            raise ValueError("hours must be between 1 and 360")
        with self.connect() as connection:
            rows = connection.execute(
                """WITH latest AS (
                    SELECT provider,location_id,MAX(retrieved_at_utc) AS retrieved_at_utc
                    FROM forecast_runs WHERE location_id=? GROUP BY provider,location_id
                ) SELECT r.provider,r.model_name,r.model_version,r.location_id,r.init_time_utc,r.init_time_quality,
                         r.upstream_available_at_utc,r.retrieved_at_utc,r.transport_provider,r.revision,
                         v.valid_time_utc,v.lead_hours,v.variable,v.statistic,v.value,v.unit,v.accumulation_window_minutes
                  FROM latest l JOIN forecast_runs r ON r.provider=l.provider AND r.location_id=l.location_id AND r.retrieved_at_utc=l.retrieved_at_utc
                  JOIN forecast_values v ON v.run_id=r.id
                  WHERE v.variable=? AND v.lead_hours<=? ORDER BY v.valid_time_utc,r.provider,v.statistic""",
                (location_id, variable, hours),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_forecast_rows(self, *, hours: int = 360, variables: Iterable[str], location_id: str = "home") -> list[dict[str, object]]:
        names = tuple(dict.fromkeys(variables))
        if not names:
            return []
        placeholders = ",".join("?" for _ in names)
        with self.connect() as connection:
            rows = connection.execute(
                f"""WITH latest AS (
                    SELECT provider,location_id,MAX(retrieved_at_utc) AS retrieved_at_utc FROM forecast_runs
                    WHERE location_id=? GROUP BY provider,location_id
                ) SELECT r.provider,r.model_name,r.model_version,r.location_id,r.init_time_utc,r.init_time_quality,r.retrieved_at_utc,
                         v.valid_time_utc,v.lead_hours,v.variable,v.statistic,v.value,v.unit,v.accumulation_window_minutes
                  FROM latest l JOIN forecast_runs r ON r.provider=l.provider AND r.location_id=l.location_id AND r.retrieved_at_utc=l.retrieved_at_utc
                  JOIN forecast_values v ON v.run_id=r.id
                  WHERE v.variable IN ({placeholders}) AND v.lead_hours<=?
                  ORDER BY r.provider,v.valid_time_utc,v.variable,v.statistic""",
                (location_id, *names, hours),
            ).fetchall()
        return [dict(row) for row in rows]

    def temperature_verification_pairs(self, *, days: int = 90, location_id: str = "station_10416") -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """WITH forecast AS (
                    SELECT r.provider,r.model_version,r.location_id,r.init_time_quality,r.init_time_utc,r.retrieved_at_utc,
                           r.upstream_available_at_utc,v.valid_time_utc,v.lead_hours,v.value AS forecast_value,
                           MAX(CASE WHEN v.statistic='p10' THEN v.value END) OVER (PARTITION BY r.id,v.valid_time_utc,v.variable) AS p10,
                           MAX(CASE WHEN v.statistic='p90' THEN v.value END) OVER (PARTITION BY r.id,v.valid_time_utc,v.variable) AS p90,
                           v.statistic
                    FROM forecast_runs r JOIN forecast_values v ON v.run_id=r.id
                    WHERE r.location_id=? AND v.variable='temperature_2m'
                      AND v.statistic IN ('deterministic','mean','p50','p10','p90')
                      AND julianday(v.valid_time_utc)>=julianday('now',?)
                ) SELECT f.*,o.value AS observed_value,o.location_id AS truth_location_id
                  FROM forecast f JOIN observations o ON o.variable='temperature_2m'
                    AND o.observed_at_utc=f.valid_time_utc AND o.location_id=f.location_id
                    AND o.source_provider='DWD'
                  WHERE f.statistic IN ('deterministic','mean') ORDER BY f.provider,f.init_time_utc,f.valid_time_utc""",
                (location_id, f"-{days} days"),
            ).fetchall()
        return [dict(row) for row in rows]

    def precipitation_verification_pairs(self, *, days: int = 90, threshold_mm: float = 0.1, location_id: str = "station_10416") -> dict[str, list[dict[str, object]]]:
        with self.connect() as connection:
            amount = connection.execute(
                """SELECT r.provider,r.model_version,r.location_id,r.init_time_quality,r.init_time_utc,v.valid_time_utc,v.lead_hours,
                          v.value AS forecast_value,o.value AS observed_value
                   FROM forecast_runs r JOIN forecast_values v ON v.run_id=r.id
                   JOIN observations o ON o.variable='precipitation_1h' AND o.observed_at_utc=v.valid_time_utc
                     AND o.location_id=r.location_id AND o.source_provider='DWD'
                   WHERE r.location_id=? AND v.variable='precipitation_1h' AND v.statistic IN ('deterministic','mean')
                     AND v.unit='mm' AND v.accumulation_window_minutes=60 AND o.unit='mm'
                     AND julianday(v.valid_time_utc)>=julianday('now',?) ORDER BY r.provider,v.valid_time_utc""",
                (location_id, f"-{days} days"),
            ).fetchall()
            probability = connection.execute(
                """SELECT r.provider,r.model_version,r.location_id,r.init_time_quality,r.init_time_utc,v.valid_time_utc,v.lead_hours,
                          v.value/100.0 AS probability,CASE WHEN o.value>=? THEN 1.0 ELSE 0.0 END AS observed_event
                   FROM forecast_runs r JOIN forecast_values v ON v.run_id=r.id
                   JOIN observations o ON o.variable='precipitation_1h' AND o.observed_at_utc=v.valid_time_utc
                     AND o.location_id=r.location_id AND o.source_provider='DWD'
                   WHERE r.location_id=? AND v.variable='precipitation_probability_1h' AND v.unit='%'
                     AND v.accumulation_window_minutes=60 AND o.unit='mm'
                     AND julianday(v.valid_time_utc)>=julianday('now',?) ORDER BY r.provider,v.valid_time_utc""",
                (threshold_mm, location_id, f"-{days} days"),
            ).fetchall()
        return {"amount": [dict(row) for row in amount], "probability": [dict(row) for row in probability]}

    def corpus_stats(self) -> dict[str, object]:
        with self.connect() as connection:
            run_total = int(connection.execute("SELECT COUNT(*) FROM forecast_runs").fetchone()[0])
            obs_total = int(connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0])
            providers = [dict(row) for row in connection.execute(
                """SELECT provider,location_id,COUNT(*) AS runs,MIN(init_time_utc) AS first_init_time_utc,MAX(init_time_utc) AS last_init_time_utc,
                          MIN(retrieved_at_utc) AS first_retrieved_at_utc,MAX(retrieved_at_utc) AS last_retrieved_at_utc,
                          COUNT(DISTINCT model_version) AS model_versions
                   FROM forecast_runs GROUP BY provider,location_id ORDER BY provider,location_id"""
            ).fetchall()]
            obs_bounds = connection.execute("SELECT MIN(observed_at_utc),MAX(observed_at_utc) FROM observations").fetchone()
            gaps = int(connection.execute(
                """WITH ordered AS (
                    SELECT observed_at_utc,LAG(observed_at_utc) OVER (ORDER BY observed_at_utc) AS prev
                    FROM observations WHERE variable='temperature_2m' AND source_provider='DWD' AND location_id='station_10416'
                ) SELECT COUNT(*) FROM ordered WHERE prev IS NOT NULL AND (julianday(observed_at_utc)-julianday(prev))*24.0>2.01"""
            ).fetchone()[0])
        return {"forecast_runs": run_total, "observations": obs_total, "observation_first_utc": obs_bounds[0], "observation_last_utc": obs_bounds[1], "providers": providers, "observation_gaps_over_2h": gaps}

    def corpus_integrity(self) -> dict[str, object]:
        errors: list[str] = []
        with self.connect() as connection:
            duplicates = connection.execute(
                """SELECT provider,location_id,init_time_utc,raw_payload_hash,COUNT(*) AS n FROM forecast_runs
                   WHERE raw_payload_hash IS NOT NULL GROUP BY provider,location_id,init_time_utc,raw_payload_hash HAVING COUNT(*)>1"""
            ).fetchall()
            run_rows = connection.execute("SELECT id,location_id,init_time_utc,retrieved_at_utc,upstream_available_at_utc FROM forecast_runs").fetchall()
            value_rows = connection.execute("SELECT location_id,valid_time_utc,lead_hours,variable,value,unit,accumulation_window_minutes FROM forecast_values").fetchall()
            obs_rows = connection.execute("SELECT location_id,observed_at_utc,variable,value,unit FROM observations").fetchall()
        for row in duplicates:
            errors.append(f"duplicate_payload:{row['provider']}:{row['location_id']}:{row['init_time_utc']}")
        for row in run_rows:
            if not row["location_id"]:
                errors.append(f"missing_location:run:{row['id']}")
            for field in ("init_time_utc", "retrieved_at_utc"):
                if not str(row[field]).endswith("Z"):
                    errors.append(f"non_utc:{field}:run:{row['id']}")
            if row["upstream_available_at_utc"] and not str(row["upstream_available_at_utc"]).endswith("Z"):
                errors.append(f"non_utc:upstream_available_at_utc:run:{row['id']}")
        for row in value_rows:
            if not row["location_id"]:
                errors.append("missing_location:forecast_value")
            if not str(row["valid_time_utc"]).endswith("Z"):
                errors.append("non_utc:forecast_valid_time")
            errors.extend(validate_semantics(variable=str(row["variable"]), value=float(row["value"]), unit=str(row["unit"]), accumulation_window_minutes=row["accumulation_window_minutes"]))
        for row in obs_rows:
            if not str(row["observed_at_utc"]).endswith("Z"):
                errors.append("non_utc:observation_time")
            definition = VARIABLES.get(str(row["variable"]))
            if definition and str(row["unit"]) != definition["unit"]:
                errors.append(f"invalid_observation_unit:{row['variable']}:{row['unit']}")
        return {"ok": not errors, "errors": errors, "error_count": len(errors)}

    def notable_temperature_cases(self, *, days: int = 90, limit: int = 10, location_id: str = "station_10416") -> list[dict[str, object]]:
        rows = self.temperature_verification_pairs(days=days, location_id=location_id)
        return sorted(rows, key=lambda row: abs(float(row["forecast_value"]) - float(row["observed_value"])), reverse=True)[:limit]

    def backup_to(self, destination: Path) -> None:
        if self.path == ":memory:":
            raise ValueError("cannot back up an in-memory database")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as source, sqlite3.connect(destination) as target:
            source.backup(target)
