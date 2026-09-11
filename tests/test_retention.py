from __future__ import annotations

import pytest

from rozkalns_weather.retention import (
    BLOCKED_FRACTION,
    RETENTION_CLASSES,
    WARN_FRACTION,
    estimate_storage,
    evaluate_retention_readiness,
    retention_contract,
)


def _backup() -> dict[str, object]:
    return {
        "backup_present": True,
        "backup_sha256": "a" * 64,
        "corpus_manifest_sha256": "b" * 64,
        "source_sha": "c" * 40,
        "integrity_check": "ok",
        "required_tables_present": True,
    }


def _counts(**overrides: int) -> dict[str, int]:
    values = {name: 0 for name in RETENTION_CLASSES}
    values.update(overrides)
    return values


def test_contract_defines_required_retention_classes_and_no_live_authority() -> None:
    contract = retention_contract()
    assert set(contract["artifact_classes"]) == {
        "deterministic_runs",
        "ensemble_members",
        "observations",
        "verification_artifacts",
        "reports",
    }
    assert contract["artifact_classes"]["ensemble_members"]["minimum_retention_days"] == 3
    assert all(item["silent_pruning_allowed"] is False for item in contract["artifact_classes"].values())
    assert contract["authority"] == {
        "production_delete_or_prune": False,
        "backup_or_restore": False,
        "filesystem_mutation": False,
        "runtime_live": False,
    }


def test_storage_estimate_is_deterministic_and_warns_before_blocking() -> None:
    counts = _counts(deterministic_runs=3)
    estimate = estimate_storage(counts)
    total = estimate["estimated_total_bytes"]
    assert total == 3 * RETENTION_CLASSES["deterministic_runs"]["estimated_bytes_per_item"]

    warn_budget = int(total / WARN_FRACTION)
    result = evaluate_retention_readiness(
        counts=counts,
        storage_budget_bytes=warn_budget,
        backup_evidence=_backup(),
    )
    assert result["state"] == "WARN"
    assert result["warn_reasons"] == ["STORAGE_BUDGET_WARN"]
    assert result["storage"]["host_storage_inspected"] is False

    blocked_budget = int(total / BLOCKED_FRACTION)
    blocked = evaluate_retention_readiness(
        counts=counts,
        storage_budget_bytes=blocked_budget,
        backup_evidence=_backup(),
    )
    assert blocked["state"] == "BLOCKED"
    assert "STORAGE_BUDGET_BLOCKED" in blocked["block_reasons"]


def test_incomplete_backup_evidence_blocks_and_exposes_restore_preconditions_only() -> None:
    evidence = _backup()
    evidence["backup_sha256"] = ""
    evidence["required_tables_present"] = False
    result = evaluate_retention_readiness(
        counts=_counts(),
        storage_budget_bytes=1_000_000,
        backup_evidence=evidence,
    )
    assert result["state"] == "BLOCKED"
    assert "BACKUP_SHA256_INVALID" in result["block_reasons"]
    assert "BACKUP_REQUIRED_TABLES_INCOMPLETE" in result["block_reasons"]
    assert result["backup"]["backup_or_restore_performed"] is False
    assert "separate_exact_live_data_authorization" in result["backup"]["restore_preconditions"]


def test_retention_policy_conflict_blocks_silent_or_early_pruning() -> None:
    deterministic = evaluate_retention_readiness(
        counts=_counts(),
        storage_budget_bytes=1_000_000,
        backup_evidence=_backup(),
        proposed_retention={"deterministic_runs": {"retention_days": 30}},
    )
    assert "RETENTION_POLICY_CONFLICT_DETERMINISTIC_RUNS" in deterministic["block_reasons"]

    ensemble = evaluate_retention_readiness(
        counts=_counts(),
        storage_budget_bytes=1_000_000,
        backup_evidence=_backup(),
        proposed_retention={"ensemble_members": {"retention_days": 2}},
    )
    assert "RETENTION_POLICY_CONFLICT_ENSEMBLE_MEMBERS" in ensemble["block_reasons"]

    silent = evaluate_retention_readiness(
        counts=_counts(),
        storage_budget_bytes=1_000_000,
        backup_evidence=_backup(),
        proposed_retention={"ensemble_members": {"retention_days": 3, "silent_prune": True}},
    )
    assert "RETENTION_POLICY_CONFLICT_ENSEMBLE_MEMBERS" in silent["block_reasons"]


def test_unknown_artifact_classes_fail_closed() -> None:
    result = evaluate_retention_readiness(
        counts={**_counts(), "mystery_blob": 1},
        storage_budget_bytes=1_000_000,
        backup_evidence=_backup(),
        proposed_retention={"mystery_blob": {"retention_days": 1}},
    )
    assert result["state"] == "BLOCKED"
    assert "UNKNOWN_ARTIFACT_CLASS" in result["block_reasons"]
    assert "UNKNOWN_RETENTION_ARTIFACT_CLASS" in result["block_reasons"]
    assert result["inventory"]["unknown_artifact_classes"] == ["mystery_blob"]


def test_private_backup_evidence_is_rejected_without_echoing_values() -> None:
    evidence = _backup()
    evidence["database_path"] = "/private/weather.db"
    result = evaluate_retention_readiness(
        counts=_counts(),
        storage_budget_bytes=1_000_000,
        backup_evidence=evidence,
    )
    assert result["state"] == "BLOCKED"
    assert result["block_reasons"] == ["FORBIDDEN_PRIVATE_BACKUP_EVIDENCE"]
    assert "/private/weather.db" not in repr(result)


def test_invalid_counts_raise_for_direct_estimator() -> None:
    with pytest.raises(ValueError):
        estimate_storage({"deterministic_runs": -1})
