from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Callable, Mapping

from .corpus_manifest import EXPECTED_SCHEMA_COLUMNS, build_corpus_provenance_manifest
from .db import Database
from .locations import DWD_10416
from .models import ForecastRun, ForecastValue
from .providers.open_meteo import ECMWF_IFS
from .retention import RETENTION_CLASSES, evaluate_retention_readiness

CONTRACT = "recovery-readiness-fault-injection-v1"
SCHEMA_VERSION = 1
WINDOW_DATE = date(2026, 4, 2)
SYNTHETIC_SOURCE_SHA = "1" * 40
ALTERNATE_SOURCE_SHA = "2" * 40
SCENARIOS = (
    "valid_backup",
    "truncated_sqlite",
    "checksum_mismatch",
    "missing_required_table",
    "broken_provenance_chain",
    "incompatible_schema_identity",
    "ambiguous_source_identity",
    "missing_metadata",
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _database(path: Path) -> Database:
    return Database(f"sqlite:///{path}")


def _reference_fixture(path: Path) -> dict[str, object]:
    database = _database(path)
    database.initialize()
    database.ensure_location(
        location_id=DWD_10416.id,
        label=DWD_10416.label,
        lat=DWD_10416.lat,
        lon=DWD_10416.lon,
        elevation_m=DWD_10416.elevation_m,
        timezone=DWD_10416.timezone,
    )
    init = datetime(2026, 4, 2, 0, tzinfo=timezone.utc)
    database.insert_forecast_run(
        ForecastRun(
            provider=ECMWF_IFS.provider_id,
            model_provider=ECMWF_IFS.model_provider,
            model_name=ECMWF_IFS.model_name,
            model_version="synthetic-recovery-fixture-v1",
            init_time_utc=init,
            retrieved_at_utc=init + timedelta(minutes=5),
            init_time_quality="single_runs_explicit",
            source_surface="synthetic-recovery-fixture",
            values=(
                ForecastValue(
                    valid_time_utc=init + timedelta(hours=6),
                    lead_hours=6.0,
                    variable="temperature_2m",
                    value=10.0,
                    unit="degC",
                ),
            ),
        ),
        location_id=DWD_10416.id,
    )
    manifest = build_corpus_provenance_manifest(database, start=WINDOW_DATE, end=WINDOW_DATE)
    if manifest["state"] != "PASS":
        raise RuntimeError(f"reference recovery fixture must be PASS, got {manifest['state']}")
    return manifest


def _quick_check(path: Path) -> tuple[bool, list[str], set[str]]:
    try:
        connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        try:
            rows = [str(row[0]) for row in connection.execute("PRAGMA quick_check").fetchall()]
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            }
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        return False, ["SQLITE_UNREADABLE_OR_CORRUPT"], set()
    ok = rows == ["ok"]
    return ok, [] if ok else ["SQLITE_INTEGRITY_FAILED"], tables


def _empty_counts() -> dict[str, int]:
    return {name: 0 for name in RETENTION_CLASSES}


def _backup_metadata(
    *,
    candidate_path: Path,
    manifest_checksum: str,
    source_sha: object = SYNTHETIC_SOURCE_SHA,
    source_candidates: object = None,
) -> dict[str, object]:
    return {
        "backup_present": True,
        "backup_sha256": _sha256_file(candidate_path),
        "corpus_manifest_sha256": manifest_checksum,
        "source_sha": source_sha,
        "source_candidates": [SYNTHETIC_SOURCE_SHA] if source_candidates is None else source_candidates,
    }


def _fault_truncated(path: Path, metadata: dict[str, object]) -> None:
    data = path.read_bytes()
    path.write_bytes(data[: max(64, len(data) // 8)])


def _fault_checksum(path: Path, metadata: dict[str, object]) -> None:
    metadata["backup_sha256"] = "f" * 64


def _fault_missing_table(path: Path, metadata: dict[str, object]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE observations")


def _fault_broken_provenance(path: Path, metadata: dict[str, object]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """INSERT INTO forecast_runs (
                   provider,model_provider,model_name,model_version,location_id,
                   init_time_utc,retrieved_at_utc,init_time_quality,source_surface,
                   raw_payload_hash,revision,status
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ECMWF_IFS.provider_id,
                ECMWF_IFS.model_provider,
                ECMWF_IFS.model_name,
                "synthetic-recovery-fixture-v1",
                DWD_10416.id,
                "2026-04-02T00:00:00Z",
                "2026-04-02T00:10:00Z",
                "single_runs_explicit",
                "synthetic-recovery-fixture",
                "b" * 64,
                3,
                "ok",
            ),
        )


def _fault_incompatible_schema(path: Path, metadata: dict[str, object]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE incompatible_recovery_fixture (id INTEGER PRIMARY KEY)")


def _fault_ambiguous_source(path: Path, metadata: dict[str, object]) -> None:
    metadata["source_candidates"] = [SYNTHETIC_SOURCE_SHA, ALTERNATE_SOURCE_SHA]


def _fault_missing_metadata(path: Path, metadata: dict[str, object]) -> None:
    metadata["backup_sha256"] = ""
    metadata["corpus_manifest_sha256"] = ""
    metadata["source_sha"] = ""
    metadata["source_candidates"] = []


FAULTS: dict[str, Callable[[Path, dict[str, object]], None]] = {
    "truncated_sqlite": _fault_truncated,
    "checksum_mismatch": _fault_checksum,
    "missing_required_table": _fault_missing_table,
    "broken_provenance_chain": _fault_broken_provenance,
    "incompatible_schema_identity": _fault_incompatible_schema,
    "ambiguous_source_identity": _fault_ambiguous_source,
    "missing_metadata": _fault_missing_metadata,
}


def _candidate_manifest(path: Path) -> tuple[dict[str, object] | None, list[str]]:
    try:
        return (
            build_corpus_provenance_manifest(_database(path), start=WINDOW_DATE, end=WINDOW_DATE),
            [],
        )
    except (sqlite3.DatabaseError, OSError, ValueError):
        return None, ["CORPUS_MANIFEST_UNREADABLE"]


def _source_identity_reasons(metadata: Mapping[str, object]) -> list[str]:
    source_sha = metadata.get("source_sha")
    candidates = metadata.get("source_candidates")
    if not isinstance(candidates, list) or len(candidates) != 1 or candidates[0] != source_sha:
        return ["SOURCE_IDENTITY_AMBIGUOUS"]
    return []


def _inspect_candidate(
    *,
    scenario: str,
    candidate_path: Path,
    metadata: Mapping[str, object],
    reference_schema_sha256: str,
) -> dict[str, object]:
    actual_backup_sha256 = _sha256_file(candidate_path)
    quick_ok, reasons, tables = _quick_check(candidate_path)
    required_tables = set(EXPECTED_SCHEMA_COLUMNS)
    required_tables_present = required_tables.issubset(tables)
    if not required_tables_present:
        reasons.append("REQUIRED_TABLES_MISSING")

    manifest, manifest_reasons = _candidate_manifest(candidate_path)
    reasons.extend(manifest_reasons)
    actual_manifest_checksum: str | None = None
    if manifest is not None:
        actual_manifest_checksum = str(manifest["aggregate_checksum_sha256"])
        reasons.extend(str(item) for item in manifest["block_reasons"])
        if str(manifest["corpus_schema"]["identity_sha256"]) != reference_schema_sha256:
            reasons.append("SCHEMA_IDENTITY_INCOMPATIBLE")

    advertised_backup_sha = metadata.get("backup_sha256")
    if advertised_backup_sha != actual_backup_sha256:
        reasons.append("BACKUP_CHECKSUM_MISMATCH")
    advertised_manifest_sha = metadata.get("corpus_manifest_sha256")
    if actual_manifest_checksum is not None and advertised_manifest_sha != actual_manifest_checksum:
        reasons.append("CORPUS_MANIFEST_CHECKSUM_MISMATCH")
    reasons.extend(_source_identity_reasons(metadata))

    retention = evaluate_retention_readiness(
        counts=_empty_counts(),
        storage_budget_bytes=1_000_000,
        backup_evidence={
            "backup_present": metadata.get("backup_present"),
            "backup_sha256": advertised_backup_sha,
            "corpus_manifest_sha256": advertised_manifest_sha,
            "source_sha": metadata.get("source_sha"),
            "integrity_check": "ok" if quick_ok else "failed",
            "required_tables_present": required_tables_present,
        },
    )
    reasons.extend(str(item) for item in retention["block_reasons"])
    reasons = sorted(set(reasons))

    if "SOURCE_IDENTITY_AMBIGUOUS" in reasons:
        classification = "AMBIGUOUS_SOURCE_IDENTITY"
    elif "SCHEMA_IDENTITY_INCOMPATIBLE" in reasons:
        classification = "INCOMPATIBLE_SCHEMA"
    elif reasons:
        classification = "INVALID_BACKUP"
    else:
        classification = "VALID_BACKUP"

    state = "PASS" if classification == "VALID_BACKUP" else "BLOCKED"
    return {
        "scenario": scenario,
        "state": state,
        "classification": classification,
        "reason_codes": reasons,
        "validators": {
            "sqlite_quick_check": "PASS" if quick_ok else "BLOCKED",
            "retention_readiness": str(retention["state"]),
            "corpus_manifest": "UNREADABLE" if manifest is None else str(manifest["state"]),
        },
        "source_only": True,
        "restore_performed": False,
        "production_paths_read": False,
        "production_mutation_performed": False,
    }


def run_recovery_readiness_fault_injection() -> dict[str, object]:
    """Exercise recovery-readiness validators against disposable synthetic artifacts only."""
    with tempfile.TemporaryDirectory(prefix="rozkalns-weather-recovery-") as directory:
        root = Path(directory)
        reference_path = root / "reference.db"
        reference_manifest = _reference_fixture(reference_path)
        reference_before = _sha256_file(reference_path)
        reference_schema_sha256 = str(reference_manifest["corpus_schema"]["identity_sha256"])
        reference_manifest_sha256 = str(reference_manifest["aggregate_checksum_sha256"])

        scenarios: list[dict[str, object]] = []
        for scenario in SCENARIOS:
            candidate_path = root / f"candidate-{scenario}.db"
            shutil.copyfile(reference_path, candidate_path)
            metadata = _backup_metadata(
                candidate_path=candidate_path,
                manifest_checksum=reference_manifest_sha256,
            )
            fault = FAULTS.get(scenario)
            if fault is not None:
                fault(candidate_path, metadata)
            scenarios.append(
                _inspect_candidate(
                    scenario=scenario,
                    candidate_path=candidate_path,
                    metadata=metadata,
                    reference_schema_sha256=reference_schema_sha256,
                )
            )

        reference_after = _sha256_file(reference_path)
        reference_unchanged = reference_before == reference_after

    expected = {
        item["scenario"]: item["state"]
        for item in scenarios
    }
    suite_reasons: list[str] = []
    if expected.get("valid_backup") != "PASS":
        suite_reasons.append("UNEXPECTED_SCENARIO_OUTCOME")
    for scenario in SCENARIOS:
        if scenario != "valid_backup" and expected.get(scenario) != "BLOCKED":
            suite_reasons.append("UNEXPECTED_SCENARIO_OUTCOME")
    if not reference_unchanged:
        suite_reasons.append("REFERENCE_FIXTURE_MUTATED")

    return {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "state": "BLOCKED" if suite_reasons else "PASS",
        "reason_codes": sorted(set(suite_reasons)),
        "scenarios": scenarios,
        "reference_fixture_unchanged": reference_unchanged,
        "source_only": True,
        "restore_performed": False,
        "production_paths_read": False,
        "production_mutation_performed": False,
        "authority": {
            "real_backup_verification_granted": False,
            "restore_target_selection_granted": False,
            "production_recovery_mutation_granted": False,
            "runtime_live_authority_granted": False,
        },
        "future_owner_gates": [
            "REAL_BACKUP_VERIFICATION",
            "RESTORE_TARGET_SELECTION",
            "PRODUCTION_RECOVERY_MUTATION",
        ],
    }
