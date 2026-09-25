from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from rozkalns_weather.sqlite_concurrency import (
    BUSY_TIMEOUT_MS,
    CONTRACT,
    JOURNAL_MODE,
    READER_COUNT,
    WRITE_TRANSACTION,
    build_disposable_fixture,
    competing_writers,
    failed_and_contended_writes_are_atomic,
    long_reader_writer,
    main,
    missing_schema_fails_closed,
    one_writer_many_readers,
    run_concurrency_suite,
)


def test_disposable_fixture_has_explicit_wal_contract(tmp_path: Path) -> None:
    path = tmp_path / "fixture.sqlite3"
    contract = build_disposable_fixture(path)

    assert contract == {
        "state": "PASS",
        "reason_codes": [],
        "journal_mode": JOURNAL_MODE,
        "busy_timeout_ms": BUSY_TIMEOUT_MS,
        "write_transaction": WRITE_TRANSACTION,
        "missing_tables": [],
    }

    connection = sqlite3.connect(path)
    try:
        assert str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"
        trigger_names = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name"
            )
        }
    finally:
        connection.close()
    assert "forecast_runs_no_update" in trigger_names
    assert "forecast_values_no_update" in trigger_names


def test_one_writer_many_readers_never_sees_partial_transaction(tmp_path: Path) -> None:
    result = one_writer_many_readers(tmp_path / "readers.sqlite3")

    assert result["state"] == "PASS"
    assert result["reason_codes"] == []
    assert result["evidence"]["reader_count"] == READER_COUNT
    assert result["evidence"]["before_commit_counts"] == [0] * READER_COUNT
    assert result["evidence"]["after_commit_counts"] == [1] * READER_COUNT


def test_competing_writer_timeout_is_bounded_and_clean_retry_succeeds(tmp_path: Path) -> None:
    result = competing_writers(tmp_path / "writers.sqlite3")

    assert result["state"] == "PASS"
    assert result["reason_codes"] == []
    assert result["evidence"]["first_attempt_reason"] == "WRITE_LOCK_TIMEOUT"
    assert result["evidence"]["retry_eligible"] is True
    assert result["evidence"]["retry_succeeded_after_release"] is True
    assert result["evidence"]["busy_timeout_ms"] == BUSY_TIMEOUT_MS


def test_long_reader_keeps_snapshot_without_blocking_writer(tmp_path: Path) -> None:
    result = long_reader_writer(tmp_path / "long-reader.sqlite3")

    assert result["state"] == "PASS"
    assert result["reason_codes"] == []
    assert result["evidence"]["snapshot_before"] == 0
    assert result["evidence"]["snapshot_during"] == 0
    assert result["evidence"]["visible_after_reader_commit"] == 1


def test_failed_and_contended_writes_preserve_immutable_identity(tmp_path: Path) -> None:
    result = failed_and_contended_writes_are_atomic(tmp_path / "atomicity.sqlite3")

    assert result["state"] == "PASS"
    assert result["reason_codes"] == []
    assert result["evidence"]["contended_identity_unchanged"] is True
    assert result["evidence"]["failed_transaction_reason"] == "TRANSACTION_CONSTRAINT_FAILURE"
    assert result["evidence"]["failed_identity_unchanged"] is True
    assert len(str(result["evidence"]["immutable_identity"])) == 64


def test_missing_schema_fails_closed_without_implicit_init(tmp_path: Path) -> None:
    result = missing_schema_fails_closed(tmp_path / "missing-schema.sqlite3")

    assert result["state"] == "PASS"
    assert result["reason_codes"] == []
    assert result["evidence"]["contract_state"] == "BLOCKED"
    assert "REQUIRED_SCHEMA_MISSING" in result["evidence"]["contract_reason_codes"]
    assert "UNSAFE_IMPLICIT_SCHEMA_INIT_REQUIRED" in result["evidence"]["contract_reason_codes"]
    assert result["evidence"]["tables_before"] == []
    assert result["evidence"]["tables_after"] == []


def test_machine_contract_matches_source_and_grants_no_runtime_authority() -> None:
    path = Path(__file__).resolve().parents[1] / "contracts" / "sqlite-concurrency-wal-v1.json"
    contract = json.loads(path.read_text(encoding="utf-8"))

    assert contract["contract"] == CONTRACT
    assert contract["status"] == "ACTIVE_SOURCE_GATE"
    assert contract["scope"]["synthetic_disposable_sqlite_only"] is True
    assert contract["scope"]["production_sqlite_access"] is False
    assert contract["sqlite_contract"]["journal_mode"] == JOURNAL_MODE
    assert contract["sqlite_contract"]["busy_timeout_ms"] == BUSY_TIMEOUT_MS
    assert contract["sqlite_contract"]["write_transaction"] == WRITE_TRANSACTION
    assert contract["sqlite_contract"]["reader_count"] == READER_COUNT
    assert contract["readiness_evidence"]["wall_clock_performance_is_gate"] is False
    assert contract["authority"]["production_sqlite_access_granted"] is False
    assert contract["authority"]["production_pragma_or_wal_mutation_granted"] is False
    assert contract["authority"]["runtime_live_authority_granted"] is False


def test_full_suite_is_source_only_and_separates_host_performance() -> None:
    payload = run_concurrency_suite()

    assert payload["contract"] == CONTRACT
    assert payload["state"] == "PASS"
    assert payload["block_reasons"] == []
    assert payload["blocked_scenarios"] == []
    assert payload["source_only"] is True
    assert payload["host_performance_assessed"] is False
    assert payload["production_paths_read"] is False
    assert payload["production_mutation_performed"] is False
    assert payload["authority"]["production_sqlite_access_granted"] is False
    assert payload["authority"]["production_pragma_or_wal_mutation_granted"] is False
    assert payload["authority"]["host_tuning_granted"] is False
    assert payload["authority"]["runtime_live_authority_granted"] is False
    assert [item["scenario"] for item in payload["scenarios"]] == [
        "one_writer_many_readers",
        "competing_writers",
        "long_reader_writer",
        "failed_and_contended_writes_are_atomic",
        "missing_schema_fails_closed",
    ]
    assert all(item["state"] == "PASS" for item in payload["scenarios"])


def test_cli_emits_machine_readable_source_only_evidence(capsys) -> None:
    rc = main()
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["contract"] == CONTRACT
    assert payload["state"] == "PASS"
    assert payload["source_only"] is True
    assert payload["host_performance_assessed"] is False
    assert payload["production_mutation_performed"] is False
