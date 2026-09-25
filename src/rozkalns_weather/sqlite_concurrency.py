from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Callable

from .canonical_serialization import canonical_sha256
from .db import SCHEMA_SQL

CONTRACT = "sqlite-concurrency-wal-v1"
SCHEMA_VERSION = 1
JOURNAL_MODE = "wal"
BUSY_TIMEOUT_MS = 100
WRITE_TRANSACTION = "BEGIN IMMEDIATE"
READER_COUNT = 3
REQUIRED_TABLES = frozenset(
    {
        "locations",
        "forecast_runs",
        "forecast_values",
        "observations",
        "provider_ingest_status",
        "model_events",
    }
)


def _connect(path: Path, *, busy_timeout_ms: int = BUSY_TIMEOUT_MS) -> sqlite3.Connection:
    connection = sqlite3.connect(
        str(path),
        timeout=busy_timeout_ms / 1000.0,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    return connection


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    }


def inspect_connection_contract(connection: sqlite3.Connection) -> dict[str, object]:
    journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    busy_timeout_ms = int(connection.execute("PRAGMA busy_timeout").fetchone()[0])
    tables = _table_names(connection)
    missing_tables = sorted(REQUIRED_TABLES - tables)
    reasons: list[str] = []
    if journal_mode != JOURNAL_MODE:
        reasons.append("JOURNAL_MODE_NOT_WAL")
    if busy_timeout_ms != BUSY_TIMEOUT_MS:
        reasons.append("BUSY_TIMEOUT_MISMATCH")
    if missing_tables:
        reasons.extend(["REQUIRED_SCHEMA_MISSING", "UNSAFE_IMPLICIT_SCHEMA_INIT_REQUIRED"])
    return {
        "state": "BLOCKED" if reasons else "PASS",
        "reason_codes": reasons,
        "journal_mode": journal_mode,
        "busy_timeout_ms": busy_timeout_ms,
        "write_transaction": WRITE_TRANSACTION,
        "missing_tables": missing_tables,
    }


def build_disposable_fixture(path: Path) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect(path)
    try:
        observed_mode = str(connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]).lower()
        if observed_mode != JOURNAL_MODE:
            raise RuntimeError("fixture SQLite build did not enter WAL mode")
        connection.executescript(SCHEMA_SQL)
        connection.execute(
            "INSERT INTO locations(id,label,lat,lon,timezone) VALUES(?,?,?,?,?)",
            ("station_fixture", "Synthetic concurrency fixture", 51.5, 7.6, "Europe/Berlin"),
        )
        connection.execute(
            """INSERT INTO forecast_runs(
                   provider,model_provider,model_name,model_version,location_id,
                   init_time_utc,retrieved_at_utc,init_time_quality,source_surface,
                   raw_payload_hash,revision,status
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "fixture_provider",
                "fixture_provider",
                "FIXTURE",
                "fixture-v1",
                "station_fixture",
                "2026-09-25T00:00:00Z",
                "2026-09-25T00:05:00Z",
                "exact",
                "synthetic-fixture",
                "baseline-immutable-identity",
                1,
                "ok",
            ),
        )
        run_id = int(connection.execute("SELECT id FROM forecast_runs").fetchone()[0])
        connection.execute(
            """INSERT INTO forecast_values(
                   run_id,location_id,valid_time_utc,lead_hours,variable,statistic,value,unit
               ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                run_id,
                "station_fixture",
                "2026-09-25T00:00:00Z",
                0.0,
                "temperature_2m",
                "deterministic",
                10.0,
                "C",
            ),
        )
        return inspect_connection_contract(connection)
    finally:
        connection.close()


def immutable_identity(connection: sqlite3.Connection) -> str:
    runs = [
        dict(row)
        for row in connection.execute(
            """SELECT provider,model_provider,model_name,model_version,location_id,
                      init_time_utc,retrieved_at_utc,raw_payload_hash,revision,status
               FROM forecast_runs ORDER BY id"""
        )
    ]
    values = [
        dict(row)
        for row in connection.execute(
            """SELECT run_id,location_id,valid_time_utc,lead_hours,variable,statistic,
                      value,unit,accumulation_window_minutes
               FROM forecast_values ORDER BY id"""
        )
    ]
    return canonical_sha256({"forecast_runs": runs, "forecast_values": values})


def _is_lock_timeout(error: sqlite3.OperationalError) -> bool:
    detail = str(error).lower()
    return "database is locked" in detail or "database table is locked" in detail


def _scenario_result(name: str, *, passed: bool, reasons: list[str], evidence: dict[str, object]) -> dict[str, object]:
    return {
        "scenario": name,
        "state": "PASS" if passed else "BLOCKED",
        "reason_codes": reasons,
        "evidence": evidence,
    }


def one_writer_many_readers(path: Path) -> dict[str, object]:
    build_disposable_fixture(path)
    writer = _connect(path)
    readers = [_connect(path) for _ in range(READER_COUNT)]
    reasons: list[str] = []
    try:
        contract = inspect_connection_contract(writer)
        if contract["state"] != "PASS":
            reasons.extend(str(item) for item in contract["reason_codes"])
        writer.execute(WRITE_TRANSACTION)
        writer.execute(
            """INSERT INTO provider_ingest_status(
                   provider,model_name,last_attempt_at_utc,last_success_at_utc,last_init_time_utc,state,detail
               ) VALUES(?,?,?,?,?,?,?)""",
            (
                "fixture_provider",
                "FIXTURE",
                "2026-09-25T00:06:00Z",
                "2026-09-25T00:06:00Z",
                "2026-09-25T00:00:00Z",
                "ok",
                "uncommitted writer fixture",
            ),
        )
        before_commit = [
            int(reader.execute("SELECT COUNT(*) FROM provider_ingest_status").fetchone()[0])
            for reader in readers
        ]
        if before_commit != [0] * READER_COUNT:
            reasons.append("PARTIAL_TRANSACTION_VISIBLE")
        writer.execute("COMMIT")
        after_commit = [
            int(reader.execute("SELECT COUNT(*) FROM provider_ingest_status").fetchone()[0])
            for reader in readers
        ]
        if after_commit != [1] * READER_COUNT:
            reasons.append("COMMITTED_WRITE_NOT_VISIBLE")
        return _scenario_result(
            "one_writer_many_readers",
            passed=not reasons,
            reasons=reasons,
            evidence={
                "reader_count": READER_COUNT,
                "before_commit_counts": before_commit,
                "after_commit_counts": after_commit,
                "contract": contract,
            },
        )
    finally:
        try:
            writer.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
        writer.close()
        for reader in readers:
            reader.close()


def competing_writers(path: Path) -> dict[str, object]:
    build_disposable_fixture(path)
    holder = _connect(path)
    contender = _connect(path)
    reasons: list[str] = []
    timeout_classification: str | None = None
    retry_succeeded = False
    try:
        holder.execute(WRITE_TRANSACTION)
        holder.execute(
            "INSERT INTO model_events(provider,model_version,effective_at_utc,event_type,note) VALUES(?,?,?,?,?)",
            ("holder", "v1", "2026-09-25T01:00:00Z", "fixture", "lock holder"),
        )
        try:
            contender.execute(WRITE_TRANSACTION)
        except sqlite3.OperationalError as error:
            if _is_lock_timeout(error):
                timeout_classification = "WRITE_LOCK_TIMEOUT"
            else:
                reasons.append("UNEXPECTED_SQLITE_OPERATIONAL_ERROR")
        else:
            contender.execute("ROLLBACK")
            reasons.append("CONTENTION_NOT_DETECTED")

        if timeout_classification != "WRITE_LOCK_TIMEOUT":
            reasons.append("BOUNDED_LOCK_TIMEOUT_NOT_PROVEN")

        holder.execute("COMMIT")
        try:
            contender.execute(WRITE_TRANSACTION)
            contender.execute(
                "INSERT INTO model_events(provider,model_version,effective_at_utc,event_type,note) VALUES(?,?,?,?,?)",
                ("contender", "v1", "2026-09-25T01:05:00Z", "fixture", "clean retry"),
            )
            contender.execute("COMMIT")
            retry_succeeded = True
        except sqlite3.Error:
            try:
                contender.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            reasons.append("WRITER_STARVATION")

        return _scenario_result(
            "competing_writers",
            passed=not reasons,
            reasons=reasons,
            evidence={
                "first_attempt_reason": timeout_classification,
                "retry_eligible": timeout_classification == "WRITE_LOCK_TIMEOUT",
                "retry_succeeded_after_release": retry_succeeded,
                "busy_timeout_ms": BUSY_TIMEOUT_MS,
            },
        )
    finally:
        for connection in (holder, contender):
            try:
                connection.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            connection.close()


def long_reader_writer(path: Path) -> dict[str, object]:
    build_disposable_fixture(path)
    reader = _connect(path)
    writer = _connect(path)
    reasons: list[str] = []
    try:
        reader.execute("BEGIN")
        snapshot_before = int(reader.execute("SELECT COUNT(*) FROM model_events").fetchone()[0])
        try:
            writer.execute(WRITE_TRANSACTION)
            writer.execute(
                "INSERT INTO model_events(provider,model_version,effective_at_utc,event_type,note) VALUES(?,?,?,?,?)",
                ("writer", "v1", "2026-09-25T02:00:00Z", "fixture", "writer during long read"),
            )
            writer.execute("COMMIT")
        except sqlite3.OperationalError:
            try:
                writer.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            reasons.append("LONG_READER_BLOCKED_WRITER")
        snapshot_during = int(reader.execute("SELECT COUNT(*) FROM model_events").fetchone()[0])
        if snapshot_during != snapshot_before:
            reasons.append("READER_SNAPSHOT_CHANGED_MID_TRANSACTION")
        reader.execute("COMMIT")
        visible_after = int(reader.execute("SELECT COUNT(*) FROM model_events").fetchone()[0])
        if not reasons and visible_after != snapshot_before + 1:
            reasons.append("COMMITTED_WRITE_NOT_VISIBLE")
        return _scenario_result(
            "long_reader_writer",
            passed=not reasons,
            reasons=reasons,
            evidence={
                "snapshot_before": snapshot_before,
                "snapshot_during": snapshot_during,
                "visible_after_reader_commit": visible_after,
            },
        )
    finally:
        for connection in (reader, writer):
            try:
                connection.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            connection.close()


def failed_and_contended_writes_are_atomic(path: Path) -> dict[str, object]:
    build_disposable_fixture(path)
    observer = _connect(path)
    holder = _connect(path)
    contender = _connect(path)
    reasons: list[str] = []
    try:
        identity_before = immutable_identity(observer)
        holder.execute(WRITE_TRANSACTION)
        holder.execute(
            "INSERT INTO model_events(provider,model_version,effective_at_utc,event_type,note) VALUES(?,?,?,?,?)",
            ("holder", "v1", "2026-09-25T03:00:00Z", "fixture", "contention lock"),
        )
        try:
            contender.execute(WRITE_TRANSACTION)
        except sqlite3.OperationalError as error:
            if not _is_lock_timeout(error):
                reasons.append("UNEXPECTED_SQLITE_OPERATIONAL_ERROR")
        else:
            contender.execute("ROLLBACK")
            reasons.append("CONTENTION_NOT_DETECTED")
        identity_after_contention = immutable_identity(observer)
        if identity_after_contention != identity_before:
            reasons.append("CONTENDED_WRITE_CHANGED_IMMUTABLE_IDENTITY")
        holder.execute("COMMIT")

        failed_transaction_reason: str | None = None
        try:
            contender.execute(WRITE_TRANSACTION)
            cursor = contender.execute(
                """INSERT INTO forecast_runs(
                       provider,model_provider,model_name,model_version,location_id,
                       init_time_utc,retrieved_at_utc,init_time_quality,source_surface,
                       raw_payload_hash,revision,status
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "candidate",
                    "candidate",
                    "CANDIDATE",
                    "v1",
                    "station_fixture",
                    "2026-09-25T06:00:00Z",
                    "2026-09-25T06:05:00Z",
                    "exact",
                    "synthetic-fixture",
                    "candidate-identity",
                    1,
                    "ok",
                ),
            )
            run_id = int(cursor.lastrowid)
            row = (
                run_id,
                "station_fixture",
                "2026-09-25T06:00:00Z",
                0.0,
                "temperature_2m",
                "deterministic",
                11.0,
                "C",
            )
            contender.execute(
                """INSERT INTO forecast_values(
                       run_id,location_id,valid_time_utc,lead_hours,variable,statistic,value,unit
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                row,
            )
            contender.execute(
                """INSERT INTO forecast_values(
                       run_id,location_id,valid_time_utc,lead_hours,variable,statistic,value,unit
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                row,
            )
            contender.execute("COMMIT")
            reasons.append("FAILED_WRITE_NOT_TRIGGERED")
        except sqlite3.IntegrityError:
            failed_transaction_reason = "TRANSACTION_CONSTRAINT_FAILURE"
            contender.execute("ROLLBACK")

        identity_after_failed_write = immutable_identity(observer)
        if identity_after_failed_write != identity_before:
            reasons.append("FAILED_WRITE_CHANGED_IMMUTABLE_IDENTITY")
        return _scenario_result(
            "failed_and_contended_writes_are_atomic",
            passed=not reasons,
            reasons=reasons,
            evidence={
                "contended_identity_unchanged": identity_after_contention == identity_before,
                "failed_transaction_reason": failed_transaction_reason,
                "failed_identity_unchanged": identity_after_failed_write == identity_before,
                "immutable_identity": identity_before,
            },
        )
    finally:
        for connection in (observer, holder, contender):
            try:
                connection.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            connection.close()


def missing_schema_fails_closed(path: Path) -> dict[str, object]:
    connection = _connect(path)
    try:
        before = sorted(_table_names(connection))
        contract = inspect_connection_contract(connection)
        after = sorted(_table_names(connection))
        reasons: list[str] = []
        if contract["state"] != "BLOCKED":
            reasons.append("MISSING_SCHEMA_NOT_BLOCKED")
        expected = {"REQUIRED_SCHEMA_MISSING", "UNSAFE_IMPLICIT_SCHEMA_INIT_REQUIRED"}
        if not expected.issubset(set(str(item) for item in contract["reason_codes"])):
            reasons.append("MISSING_SCHEMA_REASON_INCOMPLETE")
        if before != after:
            reasons.append("IMPLICIT_SCHEMA_MUTATION_DETECTED")
        return _scenario_result(
            "missing_schema_fails_closed",
            passed=not reasons,
            reasons=reasons,
            evidence={
                "contract_state": contract["state"],
                "contract_reason_codes": contract["reason_codes"],
                "tables_before": before,
                "tables_after": after,
            },
        )
    finally:
        connection.close()


SCENARIOS: tuple[tuple[str, Callable[[Path], dict[str, object]]], ...] = (
    ("one_writer_many_readers", one_writer_many_readers),
    ("competing_writers", competing_writers),
    ("long_reader_writer", long_reader_writer),
    ("failed_and_contended_writes_are_atomic", failed_and_contended_writes_are_atomic),
    ("missing_schema_fails_closed", missing_schema_fails_closed),
)


def run_concurrency_suite() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="rozkalns-weather-sqlite-concurrency-") as directory:
        root = Path(directory)
        results = [runner(root / f"{name}.sqlite3") for name, runner in SCENARIOS]
    blocked = [item["scenario"] for item in results if item["state"] != "PASS"]
    return {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "state": "BLOCKED" if blocked else "PASS",
        "block_reasons": ["CONCURRENCY_SCENARIO_FAILED"] if blocked else [],
        "blocked_scenarios": blocked,
        "sqlite_contract": {
            "journal_mode": JOURNAL_MODE,
            "busy_timeout_ms": BUSY_TIMEOUT_MS,
            "write_transaction": WRITE_TRANSACTION,
            "reader_count": READER_COUNT,
        },
        "scenarios": results,
        "source_only": True,
        "host_performance_assessed": False,
        "production_paths_read": False,
        "production_mutation_performed": False,
        "retry_policy": {
            "write_lock_timeout": "clean_retry_eligible_after_lock_release",
            "unexpected_operational_error": "not_automatically_retryable",
        },
        "authority": {
            "production_sqlite_access_granted": False,
            "production_pragma_or_wal_mutation_granted": False,
            "host_tuning_granted": False,
            "runtime_live_authority_granted": False,
        },
    }


def main() -> int:
    payload = run_concurrency_suite()
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0 if payload["state"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
