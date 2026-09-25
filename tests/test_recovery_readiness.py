from __future__ import annotations

import json
from pathlib import Path

from rozkalns_weather.recovery_readiness import (
    CONTRACT,
    SCENARIOS,
    run_recovery_readiness_fault_injection,
)


def _scenarios(report: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        str(item["scenario"]): item
        for item in report["scenarios"]  # type: ignore[index]
    }


def test_contract_declares_source_only_fault_scenarios_and_future_owner_gates() -> None:
    contract = json.loads(Path("contracts/recovery-readiness-fault-injection-v1.json").read_text(encoding="utf-8"))

    assert contract["contract"] == CONTRACT
    assert tuple(contract["scenarios"]) == SCENARIOS
    assert contract["scope"] == {
        "synthetic_disposable_artifacts_only": True,
        "production_paths_allowed": False,
        "production_backup_or_restore_allowed": False,
        "runtime_live_authority_granted": False,
    }
    assert set(contract["future_owner_gates"]) == {
        "REAL_BACKUP_VERIFICATION",
        "RESTORE_TARGET_SELECTION",
        "PRODUCTION_RECOVERY_MUTATION",
    }
    assert contract["authority"]["production_recovery_mutation_granted"] is False


def test_suite_pass_means_valid_fixture_passes_and_every_fault_blocks() -> None:
    report = run_recovery_readiness_fault_injection()
    scenarios = _scenarios(report)

    assert report["state"] == "PASS"
    assert report["reason_codes"] == []
    assert scenarios["valid_backup"]["state"] == "PASS"
    assert scenarios["valid_backup"]["classification"] == "VALID_BACKUP"
    assert scenarios["valid_backup"]["reason_codes"] == []
    for name in SCENARIOS:
        if name != "valid_backup":
            assert scenarios[name]["state"] == "BLOCKED"


def test_truncated_sqlite_and_checksum_mismatch_fail_closed() -> None:
    scenarios = _scenarios(run_recovery_readiness_fault_injection())

    truncated = scenarios["truncated_sqlite"]
    assert truncated["classification"] == "INVALID_BACKUP"
    assert (
        "SQLITE_UNREADABLE_OR_CORRUPT" in truncated["reason_codes"]
        or "SQLITE_INTEGRITY_FAILED" in truncated["reason_codes"]
    )
    assert "BACKUP_CHECKSUM_MISMATCH" in truncated["reason_codes"]

    checksum = scenarios["checksum_mismatch"]
    assert checksum["state"] == "BLOCKED"
    assert checksum["classification"] == "INVALID_BACKUP"
    assert "BACKUP_CHECKSUM_MISMATCH" in checksum["reason_codes"]


def test_missing_table_broken_provenance_and_schema_identity_are_detected() -> None:
    scenarios = _scenarios(run_recovery_readiness_fault_injection())

    missing_table = scenarios["missing_required_table"]
    assert missing_table["state"] == "BLOCKED"
    assert "REQUIRED_TABLES_MISSING" in missing_table["reason_codes"]
    assert "BACKUP_REQUIRED_TABLES_INCOMPLETE" in missing_table["reason_codes"]

    broken_chain = scenarios["broken_provenance_chain"]
    assert broken_chain["state"] == "BLOCKED"
    assert "BROKEN_REVISION_CHAIN" in broken_chain["reason_codes"]

    incompatible = scenarios["incompatible_schema_identity"]
    assert incompatible["state"] == "BLOCKED"
    assert incompatible["classification"] == "INCOMPATIBLE_SCHEMA"
    assert "SCHEMA_IDENTITY_INCOMPATIBLE" in incompatible["reason_codes"]
    assert "SCHEMA_TABLE_SET_MISMATCH" in incompatible["reason_codes"]


def test_ambiguous_source_and_missing_metadata_cannot_be_promoted_to_pass() -> None:
    scenarios = _scenarios(run_recovery_readiness_fault_injection())

    ambiguous = scenarios["ambiguous_source_identity"]
    assert ambiguous["state"] == "BLOCKED"
    assert ambiguous["classification"] == "AMBIGUOUS_SOURCE_IDENTITY"
    assert "SOURCE_IDENTITY_AMBIGUOUS" in ambiguous["reason_codes"]

    missing = scenarios["missing_metadata"]
    assert missing["state"] == "BLOCKED"
    assert "SOURCE_IDENTITY_AMBIGUOUS" in missing["reason_codes"]
    assert "BACKUP_SHA256_INVALID" in missing["reason_codes"]
    assert "CORPUS_MANIFEST_SHA256_INVALID" in missing["reason_codes"]
    assert "BACKUP_SOURCE_SHA_INVALID" in missing["reason_codes"]


def test_recovery_planning_is_deterministic_and_never_mutates_reference_or_production() -> None:
    first = run_recovery_readiness_fault_injection()
    second = run_recovery_readiness_fault_injection()

    assert first == second
    assert first["reference_fixture_unchanged"] is True
    assert first["source_only"] is True
    assert first["restore_performed"] is False
    assert first["production_paths_read"] is False
    assert first["production_mutation_performed"] is False
    assert first["authority"] == {
        "real_backup_verification_granted": False,
        "restore_target_selection_granted": False,
        "production_recovery_mutation_granted": False,
        "runtime_live_authority_granted": False,
    }
    for scenario in first["scenarios"]:
        assert scenario["source_only"] is True
        assert scenario["restore_performed"] is False
        assert scenario["production_paths_read"] is False
        assert scenario["production_mutation_performed"] is False
