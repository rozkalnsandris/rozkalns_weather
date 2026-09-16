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
COMMON_SAMPLE_SHA = "d" * 64


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


def _artifact() -> dict[str, object]:
    return {
        "report_type": "station_benchmark_monthly_v3",
        "month": "2026-09",
        "common_sample_leaderboard": [
            {
                "provider": "weathernext3",
                "model_version": "3.0.0",
                "lead_bucket": "6-12h",
                "n": 30,
                "mae": 1.0,
            }
        ],
    }


def _kwargs() -> dict[str, object]:
    return {
        "artifact": _artifact(),
        "source_sha": SOURCE_SHA,
        "report_schema": {"name": "station_benchmark_monthly", "version": 3},
        "corpus_manifest": _manifest(),
        "window": {"start": "2026-09-01", "end": "2026-09-30"},
        "provider_models": [
            {"provider": "weathernext3", "model_name": "WeatherNext 3", "model_version": "3.0.0"},
            {"provider": "icon_d2", "model_name": "ICON-D2", "model_version": None},
        ],
        "lead_filters": {"lead_buckets": ["0-6h", "6-12h", "12-24h"]},
        "sample_filters": {
            "location_id": "station_10416",
            "comparison_mode": "monthly_common_valid_time",
            "truth_source": "DWD WMO 10416",
        },
        "metric_configuration": {
            "deterministic": ["mae", "rmse", "bias"],
            "ensemble": ["crps", "wis", "brier", "reliability"],
            "weathernext_summary": ["interval_coverage", "interval_width"],
        },
        "sample_evidence": {
            "common_sample_identity_sha256": COMMON_SAMPLE_SHA,
            "sample_counts": {"weathernext3:6-12h": 30, "icon_d2:6-12h": 30},
        },
        "metric_eligibility": {
            "deterministic": ["mae", "rmse", "bias"],
            "ensemble_members": ["crps", "wis", "brier", "reliability"],
            "weathernext_summary_quantiles": ["interval_coverage", "interval_width"],
        },
        "human_readable_reference": "reports/2026-09-station-benchmark.md",
    }


def test_same_frozen_inputs_reproduce_same_receipt() -> None:
    first = build_report_lineage_receipt(**_kwargs())
    second = build_report_lineage_receipt(**_kwargs())

    assert first == second
    assert first["source_sha"] == SOURCE_SHA
    assert first["corpus_manifest"]["aggregate_checksum_sha256"] == CORPUS_SHA
    assert first["sample_evidence"]["sample_counts"]["weathernext3:6-12h"] == 30
    assert first["configuration"]["metric_eligibility"]["ensemble_members"] == [
        "brier",
        "crps",
        "reliability",
        "wis",
    ]
    assert len(first["artifact"]["machine_readable_checksum_sha256"]) == 64
    assert len(first["lineage_identity_sha256"]) == 64

    validation = validate_report_lineage_receipt(
        first,
        artifact=_artifact(),
        corpus_manifest=_manifest(),
    )
    assert validation["state"] == "PASS"
    assert validation["reproducible"] is True
    assert validation["read_only"] is True


def test_changed_artifact_or_configuration_changes_lineage_identity() -> None:
    original = build_report_lineage_receipt(**_kwargs())

    changed_artifact_kwargs = _kwargs()
    changed_artifact = deepcopy(changed_artifact_kwargs["artifact"])
    changed_artifact["common_sample_leaderboard"][0]["mae"] = 1.25
    changed_artifact_kwargs["artifact"] = changed_artifact
    changed_artifact_receipt = build_report_lineage_receipt(**changed_artifact_kwargs)

    changed_config_kwargs = _kwargs()
    changed_config = deepcopy(changed_config_kwargs["metric_configuration"])
    changed_config["deterministic"] = ["mae", "rmse", "bias", "max_abs_error"]
    changed_config_kwargs["metric_configuration"] = changed_config
    changed_config_receipt = build_report_lineage_receipt(**changed_config_kwargs)

    assert changed_artifact_receipt["artifact"]["machine_readable_checksum_sha256"] != original["artifact"][
        "machine_readable_checksum_sha256"
    ]
    assert changed_artifact_receipt["lineage_identity_sha256"] != original["lineage_identity_sha256"]
    assert changed_config_receipt["configuration_sha256"] != original["configuration_sha256"]
    assert changed_config_receipt["lineage_identity_sha256"] != original["lineage_identity_sha256"]


def test_rejects_stale_or_mismatched_corpus_manifest() -> None:
    blocked = _kwargs()
    blocked_manifest = _manifest()
    blocked_manifest["state"] = "BLOCKED"
    blocked["corpus_manifest"] = blocked_manifest
    with pytest.raises(ReportLineageError, match="PASS or WARN") as blocked_error:
        build_report_lineage_receipt(**blocked)
    assert blocked_error.value.reason_code == "CORPUS_MANIFEST_NOT_ADMISSIBLE"

    mismatched = _kwargs()
    mismatched["window"] = {"start": "2026-09-02", "end": "2026-09-30"}
    with pytest.raises(ReportLineageError, match="exactly match") as window_error:
        build_report_lineage_receipt(**mismatched)
    assert window_error.value.reason_code == "CORPUS_WINDOW_MISMATCH"


def test_rejects_missing_provenance_and_unsupported_metric_semantics() -> None:
    missing = _kwargs()
    missing_manifest = _manifest()
    del missing_manifest["aggregate_checksum_sha256"]
    missing["corpus_manifest"] = missing_manifest
    with pytest.raises(ReportLineageError) as provenance_error:
        build_report_lineage_receipt(**missing)
    assert provenance_error.value.reason_code == "MISSING_CORPUS_PROVENANCE"

    unsupported = _kwargs()
    unsupported["metric_eligibility"] = {
        "deterministic": ["mae"],
        "ensemble_members": ["crps"],
        "weathernext_summary_quantiles": ["interval_coverage"],
        "synthetic_probability": ["brier"],
    }
    with pytest.raises(ReportLineageError) as metric_error:
        build_report_lineage_receipt(**unsupported)
    assert metric_error.value.reason_code == "UNSUPPORTED_METRIC_SEMANTICS"


def test_rejects_mixed_source_and_configuration_identities() -> None:
    mixed_source = _kwargs()
    mixed_source["source_identities"] = [SOURCE_SHA, "e" * 40]
    with pytest.raises(ReportLineageError) as source_error:
        build_report_lineage_receipt(**mixed_source)
    assert source_error.value.reason_code == "MIXED_SOURCE_IDENTITY"

    base = build_report_lineage_receipt(**_kwargs())
    mixed_config = _kwargs()
    mixed_config["configuration_identities"] = [base["configuration_sha256"], "f" * 64]
    with pytest.raises(ReportLineageError) as config_error:
        build_report_lineage_receipt(**mixed_config)
    assert config_error.value.reason_code == "MIXED_CONFIGURATION_IDENTITY"


def test_validator_detects_artifact_and_manifest_drift() -> None:
    receipt = build_report_lineage_receipt(**_kwargs())

    changed_artifact = _artifact()
    changed_artifact["month"] = "2026-10"
    with pytest.raises(ReportLineageError) as artifact_error:
        validate_report_lineage_receipt(receipt, artifact=changed_artifact, corpus_manifest=_manifest())
    assert artifact_error.value.reason_code == "REPORT_ARTIFACT_CHECKSUM_MISMATCH"

    changed_manifest = _manifest()
    changed_manifest["aggregate_checksum_sha256"] = "1" * 64
    with pytest.raises(ReportLineageError) as manifest_error:
        validate_report_lineage_receipt(receipt, artifact=_artifact(), corpus_manifest=changed_manifest)
    assert manifest_error.value.reason_code == "CORPUS_MANIFEST_MISMATCH"


def test_human_reference_is_privacy_safe_relative_identifier() -> None:
    absolute = _kwargs()
    absolute["human_readable_reference"] = "/home/andris/private/report.md"
    with pytest.raises(ReportLineageError) as absolute_error:
        build_report_lineage_receipt(**absolute)
    assert absolute_error.value.reason_code == "UNSAFE_HUMAN_REFERENCE"

    url = _kwargs()
    url["human_readable_reference"] = "https://private.example/report"
    with pytest.raises(ReportLineageError) as url_error:
        build_report_lineage_receipt(**url)
    assert url_error.value.reason_code == "UNSAFE_HUMAN_REFERENCE"
