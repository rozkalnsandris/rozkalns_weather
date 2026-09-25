from __future__ import annotations

from copy import deepcopy

import pytest

from rozkalns_weather.report_lineage import build_report_lineage_receipt, validate_report_lineage_receipt
from rozkalns_weather.report_resampling import (
    ReportResamplingError,
    bind_resampling_receipts_to_report_lineage,
)
from rozkalns_weather.verification_resampling import build_resampling_receipt


SOURCE_SHA = "a" * 40
SCHEMA_SHA = "b" * 64
CORPUS_SHA = "c" * 64
COMMON_SAMPLE_SHA = "d" * 64
TRUTH_REVISION_SHA = "e" * 64


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


def _truth_revisions() -> dict[str, object]:
    return {
        "schema_version": 1,
        "contract": "dwd-observation-revision-v1",
        "state": "PASS",
        "read_only": True,
        "verification_ready": True,
        "station_id": "05480",
        "location_id": "station_05480",
        "retrieval_count": 2,
        "sample_count": 30,
        "truth_revision_set_sha256": TRUTH_REVISION_SHA,
        "reason_codes": [],
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


def _lineage() -> dict[str, object]:
    return build_report_lineage_receipt(
        artifact=_artifact(),
        source_sha=SOURCE_SHA,
        report_schema={"name": "station_benchmark_monthly", "version": 3},
        corpus_manifest=_manifest(),
        truth_revision_set=_truth_revisions(),
        window={"start": "2026-09-01", "end": "2026-09-30"},
        provider_models=[
            {"provider": "weathernext3", "model_name": "WeatherNext 3", "model_version": "3.0.0"},
            {"provider": "icon_d2", "model_name": "ICON-D2", "model_version": None},
        ],
        lead_filters={"lead_buckets": ["0-6h", "6-12h", "12-24h"]},
        sample_filters={
            "location_id": "station_05480",
            "comparison_mode": "monthly_common_valid_time",
            "truth_source": "DWD CDC 05480",
        },
        metric_configuration={
            "deterministic": ["mae", "rmse", "bias"],
            "ensemble": ["crps", "wis", "brier", "reliability"],
            "weathernext_summary": ["interval_coverage", "interval_width"],
        },
        sample_evidence={
            "common_sample_identity_sha256": COMMON_SAMPLE_SHA,
            "sample_counts": {"weathernext3:6-12h": 30, "icon_d2:6-12h": 30},
        },
        metric_eligibility={
            "deterministic": ["mae", "rmse", "bias"],
            "ensemble_members": ["crps", "wis", "brier", "reliability"],
            "weathernext_summary_quantiles": ["interval_coverage", "interval_width"],
        },
        human_readable_reference="reports/2026-09-station-benchmark.md",
    )


def _resampling_receipt(*, lead_bucket: str = "6-12h") -> dict[str, object]:
    samples = [
        {"sample_id": f"valid-2026-09-{index:02d}", "value": float((index % 5) - 2)}
        for index in range(30)
    ]
    return build_resampling_receipt(
        samples=samples,
        binding={
            "provider": "weathernext3",
            "model_name": "WeatherNext 3",
            "model_version": "3.0.0",
            "lead_bucket": lead_bucket,
            "variable": "temperature_2m",
            "comparison_mode": "monthly_common_valid_time",
        },
        metric_configuration={
            "metric_id": "bias",
            "sample_semantics": "forecast_minus_observed",
        },
        statistic="mean",
        resample_count=100,
    )


def test_resampling_is_bound_into_existing_report_lineage_and_still_validates() -> None:
    base = _lineage()
    resampling = _resampling_receipt()
    bound = bind_resampling_receipts_to_report_lineage(base, resampling_receipts=[resampling])

    assert bound["contract"] == "verification-report-lineage-v1"
    assert bound["schema_version"] == 1
    assert bound["configuration_sha256"] != base["configuration_sha256"]
    assert bound["lineage_identity_sha256"] != base["lineage_identity_sha256"]
    lineage = bound["configuration"]["resampling"][0]
    assert lineage["algorithm"]["method"] == "sha256-index-bootstrap"
    assert lineage["algorithm"]["version"] == 1
    assert lineage["seed_identity_sha256"] == resampling["seed_identity_sha256"]
    assert lineage["sample_identity_sha256"] == resampling["sample_identity_sha256"]
    assert lineage["binding"]["provider"] == "weathernext3"
    assert lineage["binding"]["model_version"] == "3.0.0"
    assert lineage["binding"]["lead_bucket"] == "6-12h"
    assert lineage["binding"]["variable"] == "temperature_2m"
    assert lineage["binding"]["comparison_mode"] == "monthly_common_valid_time"
    assert lineage["sample_count"] == 30
    assert lineage["ranking_verdict"] is False
    assert "interval" not in lineage

    validated = validate_report_lineage_receipt(
        bound,
        artifact=_artifact(),
        corpus_manifest=_manifest(),
        truth_revision_set=_truth_revisions(),
    )
    assert validated["state"] == "PASS"
    assert validated["lineage_identity_sha256"] == bound["lineage_identity_sha256"]


def test_resampling_binding_is_order_independent_for_multiple_receipts() -> None:
    base = _lineage()
    first = _resampling_receipt(lead_bucket="6-12h")
    second = _resampling_receipt(lead_bucket="12-24h")

    left = bind_resampling_receipts_to_report_lineage(base, resampling_receipts=[first, second])
    right = bind_resampling_receipts_to_report_lineage(base, resampling_receipts=[second, first])

    assert left == right
    identities = [
        item["resampling_receipt_identity_sha256"]
        for item in left["configuration"]["resampling"]
    ]
    assert identities == sorted(identities)


def test_missing_resampling_receipt_fails_closed() -> None:
    with pytest.raises(ReportResamplingError) as error:
        bind_resampling_receipts_to_report_lineage(_lineage(), resampling_receipts=[])
    assert error.value.reason_code == "MISSING_RESAMPLING_LINEAGE"


def test_tampered_base_lineage_fails_closed_before_binding() -> None:
    tampered = deepcopy(_lineage())
    tampered["configuration"]["metric_configuration"]["deterministic"].append("max_abs_error")

    with pytest.raises(ReportResamplingError) as error:
        bind_resampling_receipts_to_report_lineage(tampered, resampling_receipts=[_resampling_receipt()])
    assert error.value.reason_code == "REPORT_LINEAGE_IDENTITY_MISMATCH"


def test_existing_resampling_lineage_cannot_be_silently_replaced() -> None:
    receipt = _resampling_receipt()
    bound = bind_resampling_receipts_to_report_lineage(_lineage(), resampling_receipts=[receipt])

    with pytest.raises(ReportResamplingError) as error:
        bind_resampling_receipts_to_report_lineage(bound, resampling_receipts=[receipt])
    assert error.value.reason_code == "RESAMPLING_LINEAGE_ALREADY_BOUND"
