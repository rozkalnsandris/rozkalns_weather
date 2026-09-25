from __future__ import annotations

from copy import deepcopy

import pytest

from rozkalns_weather.report_lineage import (
    ReportLineageError,
    build_report_lineage_receipt,
    validate_report_lineage_receipt,
)

SOURCE_SHA = "a" * 40
SCHEMA_SHA = "b" * 64
CORPUS_SHA = "c" * 64
SAMPLE_SHA = "d" * 64
TRUTH_SHA = "e" * 64


def _artifact() -> dict[str, object]:
    return {
        "report_type": "station_benchmark_monthly_v3",
        "month": "2026-09",
        "common_sample_leaderboard": [],
    }


def _manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "contract": "corpus-provenance-manifest-v1",
        "state": "PASS",
        "read_only": True,
        "window": {"start": "2026-09-01", "end": "2026-09-30"},
        "corpus_schema": {"identity_sha256": SCHEMA_SHA},
        "aggregate_checksum_sha256": CORPUS_SHA,
    }


def _truth() -> dict[str, object]:
    return {
        "schema_version": 1,
        "contract": "dwd-observation-revision-v1",
        "state": "PASS",
        "read_only": True,
        "verification_ready": True,
        "station_id": "05480",
        "location_id": "station_05480",
        "truth_revision_set_sha256": TRUTH_SHA,
    }


def _kwargs() -> dict[str, object]:
    return {
        "artifact": _artifact(),
        "source_sha": SOURCE_SHA,
        "report_schema": {"name": "station_benchmark_monthly", "version": 3},
        "corpus_manifest": _manifest(),
        "truth_revision_set": _truth(),
        "window": {"start": "2026-09-01", "end": "2026-09-30"},
        "provider_models": [
            {"provider": "icon_d2", "model_name": "ICON-D2", "model_version": "2026-09"}
        ],
        "lead_filters": {"lead_buckets": ["0-6h"]},
        "sample_filters": {"location_id": "station_05480"},
        "metric_configuration": {"deterministic": ["mae"]},
        "sample_evidence": {
            "common_sample_identity_sha256": SAMPLE_SHA,
            "sample_counts": {"icon_d2:0-6h": 1},
        },
        "metric_eligibility": {
            "deterministic": ["mae"],
            "ensemble_members": ["crps"],
            "weathernext_summary_quantiles": ["interval_coverage"],
        },
        "human_readable_reference": "reports/2026-09.md",
    }


def test_lineage_binds_exact_schema_carried_by_artifact() -> None:
    receipt = build_report_lineage_receipt(**_kwargs())
    assert receipt["report_schema"] == {"name": "station_benchmark_monthly", "version": 3}
    result = validate_report_lineage_receipt(
        receipt,
        artifact=_artifact(),
        corpus_manifest=_manifest(),
        truth_revision_set=_truth(),
    )
    assert result["state"] == "PASS"
    assert result["report_schema"] == receipt["report_schema"]


def test_declared_schema_version_cannot_disagree_with_artifact_identity() -> None:
    wrong = _kwargs()
    wrong["report_schema"] = {"name": "station_benchmark_monthly", "version": 2}
    with pytest.raises(ReportLineageError) as error:
        build_report_lineage_receipt(**wrong)
    assert error.value.reason_code == "REPORT_SCHEMA_MISMATCH"


def test_validator_rejects_artifact_schema_drift_even_with_receipt_schema_unchanged() -> None:
    receipt = build_report_lineage_receipt(**_kwargs())
    changed = deepcopy(_artifact())
    changed["report_type"] = "station_benchmark_monthly_v2"
    with pytest.raises(ReportLineageError) as error:
        validate_report_lineage_receipt(
            receipt,
            artifact=changed,
            corpus_manifest=_manifest(),
            truth_revision_set=_truth(),
        )
    assert error.value.reason_code in {"UNSUPPORTED_HISTORICAL_SCHEMA", "REPORT_SCHEMA_MISMATCH"}
