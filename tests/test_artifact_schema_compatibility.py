from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from rozkalns_weather.artifact_schema_compatibility import (
    ArtifactSchemaError,
    CONTRACT,
    artifact_schema_identity,
    classify_schema_change,
    read_historical_artifact,
    validate_bundle_schema_versions,
)

FIXTURE = Path(__file__).parent / "fixtures" / "artifact_schema_compatibility_cases.json"
CONTRACT_FILE = Path(__file__).parents[1] / "contracts" / "verification-report-schema-compatibility-v1.json"


@pytest.mark.parametrize("case", json.loads(FIXTURE.read_text())["cases"], ids=lambda case: case["name"])
def test_fixture_driven_schema_change_classification(case: dict[str, object]) -> None:
    result = classify_schema_change(case["previous"], case["current"])
    assert result["contract"] == CONTRACT
    assert result["classification"] == case["expected_classification"]
    assert case["expected_reason"] in result["reason_codes"]
    assert result["state"] == ("BLOCKED" if case["expected_classification"] == "breaking" else "PASS")
    assert result["source_artifact_rewrite_performed"] is False
    assert result["human_readable_contract_evaluated"] is False
    assert len(result["evidence_sha256"]) == 64


def test_contract_registers_all_required_machine_readable_artifact_families() -> None:
    contract = json.loads(CONTRACT_FILE.read_text())
    assert contract["contract"] == CONTRACT
    assert contract["schema_version"] == 1
    assert set(contract["artifact_schemas"]) == {
        "verification_summary",
        "monthly_report",
        "benchmark_export",
        "reproducibility_receipt",
    }
    assert contract["artifact_schemas"]["verification_summary"]["version"] == 1
    assert contract["artifact_schemas"]["monthly_report"]["contract"] == "public-monthly-benchmark-report-v1"
    assert contract["artifact_schemas"]["benchmark_export"]["contract"] == "public-benchmark-export-v1"
    assert contract["artifact_schemas"]["reproducibility_receipt"]["contract"] == "verification-report-lineage-v1"
    assert contract["human_readable_output"]["compatibility_gate_scope"] is False


def test_registered_artifact_identities_are_exact_and_historical_report_type_is_readable() -> None:
    assert artifact_schema_identity({"contract": "verification-summary-v1", "schema_version": 1}) == {
        "name": "verification_summary",
        "version": 1,
        "contract": "verification-summary-v1",
    }
    assert artifact_schema_identity({"contract": "public-monthly-benchmark-report-v1", "schema_version": 1})[
        "name"
    ] == "public_monthly_benchmark_report"
    assert artifact_schema_identity({"contract": "public-benchmark-export-v1", "schema_version": 1})[
        "name"
    ] == "public_benchmark_export"
    assert artifact_schema_identity({"contract": "verification-report-lineage-v1", "schema_version": 1})[
        "name"
    ] == "verification_report_lineage"
    legacy = artifact_schema_identity({"report_type": "station_benchmark_monthly_v3"})
    assert legacy["name"] == "station_benchmark_monthly"
    assert legacy["version"] == 3
    assert legacy["historical_identity_source"] == "report_type"


def test_contract_and_version_mismatch_fails_closed() -> None:
    with pytest.raises(ArtifactSchemaError) as error:
        artifact_schema_identity({"contract": "public-benchmark-export-v1", "schema_version": 2})
    assert error.value.reason_code == "ARTIFACT_CONTRACT_VERSION_MISMATCH"

    with pytest.raises(ArtifactSchemaError) as missing:
        artifact_schema_identity({"payload": "unversioned"})
    assert missing.value.reason_code == "MISSING_ARTIFACT_SCHEMA_IDENTITY"


def test_historical_read_is_deterministic_in_memory_and_does_not_rewrite_source() -> None:
    previous = {
        "family": "monthly_report",
        "name": "public_monthly_benchmark_report",
        "contract": "public-monthly-benchmark-report-v1",
        "version": 1,
        "fields": {
            "state": {"required": True, "nullable": False, "type": "string"},
        },
    }
    current = {
        "family": "monthly_report",
        "name": "public_monthly_benchmark_report",
        "contract": "public-monthly-benchmark-report-v2",
        "version": 2,
        "fields": {
            "state": {"required": True, "nullable": False, "type": "string"},
            "diagnostic_note": {
                "required": False,
                "nullable": True,
                "type": "string",
                "default": None,
            },
        },
    }
    source = {"state": "PASS"}
    frozen = deepcopy(source)
    result = read_historical_artifact(source, source_schema=previous, current_schema=current)
    assert source == frozen
    assert result["artifact_view"] == {"state": "PASS", "diagnostic_note": None}
    assert result["source_artifact_rewrite_performed"] is False
    assert result["compatibility"]["classification"] == "additive-compatible"


def test_breaking_historical_read_is_blocked_without_mutation() -> None:
    previous = {
        "family": "verification_summary",
        "name": "verification_summary",
        "contract": "verification-summary-v1",
        "version": 1,
        "fields": {"mae": {"required": True, "nullable": True, "type": "number"}},
    }
    current = {
        "family": "verification_summary",
        "name": "verification_summary",
        "contract": "verification-summary-v2",
        "version": 2,
        "fields": {"rmse": {"required": True, "nullable": True, "type": "number"}},
    }
    source = {"mae": 1.0}
    with pytest.raises(ArtifactSchemaError) as error:
        read_historical_artifact(source, source_schema=previous, current_schema=current)
    assert error.value.reason_code == "BREAKING_SCHEMA_CHANGE"
    assert source == {"mae": 1.0}


def test_mixed_version_bundle_is_blocked() -> None:
    result = validate_bundle_schema_versions(
        [
            {"contract": "public-benchmark-export-v1", "schema_version": 1},
            {"contract": "public-monthly-benchmark-report-v1", "schema_version": 1},
        ]
    )
    assert result["state"] == "BLOCKED"
    assert result["reason_codes"] == ["MIXED_BUNDLE_SCHEMA_VERSION"]

    same = validate_bundle_schema_versions(
        [
            {"contract": "public-benchmark-export-v1", "schema_version": 1},
            {"contract": "public-benchmark-export-v1", "schema_version": 1},
        ]
    )
    assert same["state"] == "PASS"
    assert same["artifact_count"] == 2
