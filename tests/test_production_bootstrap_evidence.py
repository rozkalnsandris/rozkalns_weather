from __future__ import annotations

from datetime import timedelta
import json

import pytest

from rozkalns_weather.production_bootstrap import (
    CHECKPOINT_NAMESPACE,
    FIXED_WINDOW_END,
    FIXED_WINDOW_START,
    build_production_bootstrap_plan,
)
from rozkalns_weather.production_bootstrap_evidence import (
    DATABASE_IDENTITY,
    EVIDENCE_CONTRACT,
    SCHEMA_INIT_COMMAND,
    TARGET_ALIAS,
    validate_execution_evidence,
)


def _runs() -> list[str]:
    result: list[str] = []
    cursor = FIXED_WINDOW_START
    while cursor <= FIXED_WINDOW_END:
        for hour in (0, 6, 12, 18):
            result.append(f"{cursor.isoformat()}T{hour:02d}:00:00Z")
        cursor += timedelta(days=1)
    return result


def _plan():
    return build_production_bootstrap_plan(
        source_sha="a" * 40,
        start=FIXED_WINDOW_START,
        end=FIXED_WINDOW_END,
        recovery_decision="verified_backup_available",
    )


def _complete_evidence() -> dict[str, object]:
    plan = _plan()
    identity = plan["identity"]
    runs = _runs()

    def model_state() -> dict[str, object]:
        return {
            "location_id": identity["benchmark_location_id"],
            "completed_runs": list(runs),
            "expected_run_count": len(runs),
            "present_run_count": len(runs),
            "revision_drift_runs": [],
            "unexpected_runs": [],
            "database_ahead_of_checkpoint": False,
            "checkpoint_ahead_of_database": False,
            "write_interrupted": False,
        }

    return {
        "schema_version": 1,
        "contract": EVIDENCE_CONTRACT,
        "source_sha": "a" * 40,
        "bootstrap_fingerprint": plan["bootstrap_fingerprint"],
        "recovery_decision": "verified_backup_available",
        "target_alias": TARGET_ALIAS,
        "database_identity": DATABASE_IDENTITY,
        "identity": {
            "start_date": "2026-08-13",
            "end_date": "2026-08-26",
            "models": ["icon_d2", "ecmwf_ifs", "ecmwf_aifs"],
            "run_hours_utc": [0, 6, 12, 18],
            "benchmark_location_id": identity["benchmark_location_id"],
            "truth_station_id": identity["truth_station_id"],
            "truth_variables": list(identity["truth_variables"]),
            "recovery_decision": "verified_backup_available",
        },
        "schema": {
            "state": "ready",
            "explicit_init_completed": True,
            "implicit_migration_performed": False,
            "command": SCHEMA_INIT_COMMAND,
        },
        "truth": {
            "station_id": identity["truth_station_id"],
            "location_id": identity["benchmark_location_id"],
            "variables": list(identity["truth_variables"]),
            "completed_chunks": ["2026-08-13..2026-08-26"],
            "expected_chunk_count": 1,
            "present_chunk_count": 1,
            "database_ahead_of_checkpoint": False,
            "checkpoint_ahead_of_database": False,
            "write_interrupted": False,
        },
        "forecasts": {
            "icon_d2": model_state(),
            "ecmwf_ifs": model_state(),
            "ecmwf_aifs": model_state(),
        },
        "integrity": {"ok": True},
    }


def test_complete_execution_evidence_passes_without_granting_authority() -> None:
    result = validate_execution_evidence(_plan(), _complete_evidence())
    assert result["state"] == "PASS"
    assert result["block_reasons"] == []
    assert result["progress"]["complete"] is True
    assert result["bindings"]["truth_station_id"] == "05480"
    assert result["bindings"]["benchmark_location_id"] == "station_05480"
    assert result["bindings"]["start_date"] == "2026-08-13"
    assert result["bindings"]["end_date"] == "2026-08-26"
    assert result["authority"]["production_data_authority_granted"] is False
    assert result["authority"]["automatic_retry_allowed"] is False


def test_clean_ordered_prefix_is_in_progress_without_skip_authority() -> None:
    evidence = _complete_evidence()
    completed = evidence["forecasts"]["icon_d2"]["completed_runs"][:-4]
    evidence["forecasts"]["icon_d2"]["completed_runs"] = completed
    evidence["forecasts"]["icon_d2"]["present_run_count"] = len(completed)
    evidence["integrity"] = {"ok": None}
    result = validate_execution_evidence(_plan(), evidence)
    assert result["state"] == "IN_PROGRESS"
    assert result["block_reasons"] == []
    assert result["progress"]["complete"] is False
    assert result["authority"]["automatic_retry_allowed"] is False


def test_stale_fingerprint_wrong_source_and_recovery_decision_block() -> None:
    evidence = _complete_evidence()
    evidence["source_sha"] = "b" * 40
    evidence["bootstrap_fingerprint"] = "0" * 64
    evidence["identity"]["recovery_decision"] = "owner_accepts_proceeding_without_prewrite_backup"
    result = validate_execution_evidence(_plan(), evidence)
    assert result["state"] == "BLOCKED"
    assert "SOURCE_SHA_MISMATCH" in result["block_reasons"]
    assert "BOOTSTRAP_FINGERPRINT_MISMATCH" in result["block_reasons"]
    assert "RECOVERY_DECISION_MISMATCH" in result["block_reasons"]


def test_station_location_variable_and_checkpoint_drift_block() -> None:
    evidence = _complete_evidence()
    evidence["identity"]["truth_station_id"] = "10416"
    evidence["truth"]["location_id"] = "station_10416"
    evidence["truth"]["variables"] = ["temperature_2m"]
    evidence["forecasts"]["ecmwf_aifs"]["location_id"] = "station_10416"
    evidence["forecasts"]["ecmwf_ifs"]["database_ahead_of_checkpoint"] = True
    result = validate_execution_evidence(_plan(), evidence)
    assert result["state"] == "BLOCKED"
    assert "TRUTH_STATION_ID_MISMATCH" in result["block_reasons"]
    assert "TRUTH_LOCATION_MISMATCH" in result["block_reasons"]
    assert "TRUTH_VARIABLE_SCOPE_MISMATCH" in result["block_reasons"]
    assert "ECMWF_AIFS_LOCATION_MISMATCH" in result["block_reasons"]
    assert "CHECKPOINT_DATABASE_DIVERGENCE" in result["block_reasons"]


def test_count_revision_and_private_evidence_fail_closed() -> None:
    evidence = _complete_evidence()
    evidence["database_identity"] = "other-db"
    evidence["forecasts"]["ecmwf_aifs"]["present_run_count"] -= 1
    evidence["forecasts"]["ecmwf_aifs"]["revision_drift_runs"] = ["2026-08-13T00:00:00Z"]
    result = validate_execution_evidence(_plan(), evidence)
    assert result["state"] == "BLOCKED"
    assert "DATABASE_IDENTITY_UNBOUND" in result["block_reasons"]
    assert "ECMWF_AIFS_PRESENT_COUNT_MISMATCH" in result["block_reasons"]
    assert "ECMWF_AIFS_REVISION_DRIFT" in result["block_reasons"]

    private = _complete_evidence()
    private["database_path"] = "/private/value"
    result = validate_execution_evidence(_plan(), private)
    assert result["state"] == "BLOCKED"
    assert result["block_reasons"] == ["PRIVATE_EVIDENCE_REJECTED"]
    assert "/private/value" not in json.dumps(result)


def test_malformed_execution_evidence_fails_closed() -> None:
    evidence = _complete_evidence()
    evidence["forecasts"] = "not-an-object"
    result = validate_execution_evidence(_plan(), evidence)
    assert result["state"] == "BLOCKED"
    assert "FORECAST_EVIDENCE_MISSING" in result["block_reasons"]


def test_checkpoint_namespace_is_new_and_not_implicit_live_authority() -> None:
    assert _plan()["checkpoint_namespace"] == CHECKPOINT_NAMESPACE
    assert CHECKPOINT_NAMESPACE == "fixed-window-20260813-20260826-v1"
    assert _plan()["production_data_authority_granted"] is False
