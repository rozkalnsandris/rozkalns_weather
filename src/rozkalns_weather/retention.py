from __future__ import annotations

import re
from typing import Mapping

SCHEMA_VERSION = 1

RETENTION_CLASSES: dict[str, dict[str, object]] = {
    "deterministic_runs": {
        "retention_mode": "immutable_benchmark",
        "minimum_retention_days": None,
        "estimated_bytes_per_item": 262_144,
        "silent_pruning_allowed": False,
    },
    "ensemble_members": {
        "retention_mode": "bounded_raw_members",
        "minimum_retention_days": 3,
        "estimated_bytes_per_item": 196_608,
        "silent_pruning_allowed": False,
    },
    "observations": {
        "retention_mode": "immutable_truth",
        "minimum_retention_days": None,
        "estimated_bytes_per_item": 512,
        "silent_pruning_allowed": False,
    },
    "verification_artifacts": {
        "retention_mode": "reproducibility_evidence",
        "minimum_retention_days": None,
        "estimated_bytes_per_item": 65_536,
        "silent_pruning_allowed": False,
    },
    "reports": {
        "retention_mode": "published_or_audit_evidence",
        "minimum_retention_days": None,
        "estimated_bytes_per_item": 262_144,
        "silent_pruning_allowed": False,
    },
}

WARN_FRACTION = 0.75
BLOCKED_FRACTION = 0.90

FORBIDDEN_EVIDENCE_KEYS = {
    "path",
    "database_path",
    "host_path",
    "home_lat",
    "home_lon",
    "credential",
    "credentials",
    "token",
    "secret",
    "raw_log",
    "raw_logs",
}

RESTORE_PRECONDITIONS = (
    "separate_exact_live_data_authorization",
    "exact_reviewed_source_sha",
    "matching_corpus_manifest_sha256",
    "backup_sha256_verified",
    "sqlite_integrity_check_ok",
    "required_tables_present",
    "explicit_restore_target_identity",
    "pre_restore_snapshot_or_owner_accepted_recovery_decision",
)


def retention_contract() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "contract": "corpus-retention-readiness-v1",
        "artifact_classes": RETENTION_CLASSES,
        "storage_budget": {
            "warn_fraction": WARN_FRACTION,
            "blocked_fraction": BLOCKED_FRACTION,
            "estimation": "sum(count * fixed_estimated_bytes_per_item)",
            "host_storage_inspection": False,
        },
        "backup_readiness": {
            "required_fields": [
                "backup_present",
                "backup_sha256",
                "corpus_manifest_sha256",
                "source_sha",
                "integrity_check",
                "required_tables_present",
            ],
            "restore_preconditions": list(RESTORE_PRECONDITIONS),
        },
        "authority": {
            "production_delete_or_prune": False,
            "backup_or_restore": False,
            "filesystem_mutation": False,
            "runtime_live": False,
        },
    }


def _validate_counts(counts: Mapping[str, int]) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    unknown = sorted(set(counts) - set(RETENTION_CLASSES))
    if unknown:
        blockers.append("UNKNOWN_ARTIFACT_CLASS")
    for artifact_class, count in counts.items():
        if artifact_class in RETENTION_CLASSES and (isinstance(count, bool) or not isinstance(count, int) or count < 0):
            blockers.append(f"INVALID_COUNT_{artifact_class.upper()}")
    return blockers, unknown


def estimate_storage(counts: Mapping[str, int]) -> dict[str, object]:
    blockers, unknown = _validate_counts(counts)
    if blockers:
        raise ValueError(",".join(blockers + unknown))
    classes: dict[str, dict[str, int]] = {}
    total = 0
    for artifact_class in sorted(RETENTION_CLASSES):
        count = int(counts.get(artifact_class, 0))
        per_item = int(RETENTION_CLASSES[artifact_class]["estimated_bytes_per_item"])
        estimated = count * per_item
        total += estimated
        classes[artifact_class] = {
            "count": count,
            "estimated_bytes_per_item": per_item,
            "estimated_bytes": estimated,
        }
    return {"classes": classes, "estimated_total_bytes": total}


def _contains_forbidden_key(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_EVIDENCE_KEYS or normalized.endswith("_path"):
                return True
            if _contains_forbidden_key(child):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _valid_hex(value: object, length: int) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value))


def _backup_blockers(evidence: Mapping[str, object]) -> list[str]:
    if _contains_forbidden_key(evidence):
        return ["FORBIDDEN_PRIVATE_BACKUP_EVIDENCE"]
    blockers: list[str] = []
    if evidence.get("backup_present") is not True:
        blockers.append("BACKUP_NOT_PRESENT")
    if not _valid_hex(evidence.get("backup_sha256"), 64):
        blockers.append("BACKUP_SHA256_INVALID")
    if not _valid_hex(evidence.get("corpus_manifest_sha256"), 64):
        blockers.append("CORPUS_MANIFEST_SHA256_INVALID")
    if not _valid_hex(evidence.get("source_sha"), 40):
        blockers.append("BACKUP_SOURCE_SHA_INVALID")
    if evidence.get("integrity_check") != "ok":
        blockers.append("BACKUP_INTEGRITY_NOT_OK")
    if evidence.get("required_tables_present") is not True:
        blockers.append("BACKUP_REQUIRED_TABLES_INCOMPLETE")
    return blockers


def _retention_blockers(proposed_retention: Mapping[str, object]) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    unknown = sorted(set(proposed_retention) - set(RETENTION_CLASSES))
    if unknown:
        blockers.append("UNKNOWN_RETENTION_ARTIFACT_CLASS")
    for artifact_class, proposal in proposed_retention.items():
        if artifact_class not in RETENTION_CLASSES:
            continue
        if not isinstance(proposal, Mapping):
            blockers.append(f"INVALID_RETENTION_PROPOSAL_{artifact_class.upper()}")
            continue
        if proposal.get("silent_prune") is True:
            blockers.append(f"RETENTION_POLICY_CONFLICT_{artifact_class.upper()}")
        minimum = RETENTION_CLASSES[artifact_class]["minimum_retention_days"]
        requested_days = proposal.get("retention_days")
        if requested_days is not None:
            if isinstance(requested_days, bool) or not isinstance(requested_days, int) or requested_days < 0:
                blockers.append(f"INVALID_RETENTION_DAYS_{artifact_class.upper()}")
            elif minimum is None:
                blockers.append(f"RETENTION_POLICY_CONFLICT_{artifact_class.upper()}")
            elif requested_days < int(minimum):
                blockers.append(f"RETENTION_POLICY_CONFLICT_{artifact_class.upper()}")
    return blockers, unknown


def evaluate_retention_readiness(
    *,
    counts: Mapping[str, int],
    storage_budget_bytes: int,
    backup_evidence: Mapping[str, object],
    proposed_retention: Mapping[str, object] | None = None,
) -> dict[str, object]:
    blockers, unknown_inventory = _validate_counts(counts)
    if isinstance(storage_budget_bytes, bool) or not isinstance(storage_budget_bytes, int) or storage_budget_bytes <= 0:
        blockers.append("INVALID_STORAGE_BUDGET")

    estimate: dict[str, object]
    if any(reason.startswith("INVALID_COUNT_") for reason in blockers):
        estimate = {"classes": {}, "estimated_total_bytes": 0}
    else:
        known_counts = {key: value for key, value in counts.items() if key in RETENTION_CLASSES}
        estimate = estimate_storage(known_counts)

    total = int(estimate["estimated_total_bytes"])
    utilization = total / storage_budget_bytes if storage_budget_bytes > 0 else 1.0
    warnings: list[str] = []
    if storage_budget_bytes > 0:
        if utilization >= BLOCKED_FRACTION:
            blockers.append("STORAGE_BUDGET_BLOCKED")
        elif utilization >= WARN_FRACTION:
            warnings.append("STORAGE_BUDGET_WARN")

    backup_blockers = _backup_blockers(backup_evidence)
    blockers.extend(backup_blockers)

    retention_blockers: list[str] = []
    unknown_retention: list[str] = []
    if proposed_retention is not None:
        retention_blockers, unknown_retention = _retention_blockers(proposed_retention)
        blockers.extend(retention_blockers)

    blockers = list(dict.fromkeys(blockers))
    warnings = list(dict.fromkeys(warnings))
    state = "BLOCKED" if blockers else "WARN" if warnings else "PASS"
    return {
        "schema_version": SCHEMA_VERSION,
        "contract": "corpus-retention-readiness-v1",
        "state": state,
        "block_reasons": blockers,
        "warn_reasons": warnings,
        "inventory": {
            "unknown_artifact_classes": unknown_inventory,
            "unknown_retention_classes": unknown_retention,
        },
        "storage": {
            **estimate,
            "budget_bytes": storage_budget_bytes,
            "utilization_fraction": round(utilization, 6),
            "warn_fraction": WARN_FRACTION,
            "blocked_fraction": BLOCKED_FRACTION,
            "host_storage_inspected": False,
        },
        "backup": {
            "ready": not backup_blockers,
            "restore_preconditions": list(RESTORE_PRECONDITIONS),
            "backup_or_restore_performed": False,
        },
        "retention": {
            "silent_pruning_allowed": False,
            "immutable_benchmark_provenance_preserved": not retention_blockers,
        },
        "authority": {
            "production_delete_or_prune": False,
            "backup_or_restore": False,
            "filesystem_mutation": False,
            "runtime_live": False,
        },
        "privacy": {
            "private_paths_exposed": False,
            "credentials_exposed": False,
            "coordinates_exposed": False,
            "raw_logs_exposed": False,
        },
    }
