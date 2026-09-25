from __future__ import annotations

import json
from pathlib import Path

from rozkalns_weather.report_lineage import build_report_lineage_receipt
from rozkalns_weather.verification_watermark import build_verification_watermark
from rozkalns_weather.verification_watermark_lineage import watermark_report_lineage_inputs


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "verification_watermark_cases.json"


def _watermark(*, later: bool) -> dict[str, object]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return build_verification_watermark(
        fixture["samples"],
        as_of_utc=fixture["later_cutoff"] if later else fixture["cutoff"],
        report_generated_at_utc=fixture["report_generated_at"],
    )


def _receipt(watermark: dict[str, object]) -> dict[str, object]:
    binding = watermark_report_lineage_inputs(
        watermark,
        sample_counts={"icon_d2:0-6h": len(watermark["eligible_sample_ids"])},
    )
    sample_filters = {
        "location_id": "station_05480",
        "comparison_mode": "monthly_common_valid_time",
        "truth_source": "DWD CDC 05480",
        **binding["sample_filters"],
    }
    return build_report_lineage_receipt(
        artifact={
            "report_type": "station_benchmark_monthly_v3",
            "month": "2026-09",
            "common_sample_leaderboard": [],
        },
        source_sha="a" * 40,
        report_schema={"name": "station_benchmark_monthly", "version": 3},
        corpus_manifest={
            "schema_version": 1,
            "contract": "corpus-provenance-manifest-v1",
            "state": "PASS",
            "read_only": True,
            "window": {"start": "2026-09-01", "end": "2026-09-30"},
            "corpus_schema": {"identity_sha256": "b" * 64},
            "aggregate_checksum_sha256": "c" * 64,
        },
        truth_revision_set={
            "schema_version": 1,
            "contract": "dwd-observation-revision-v1",
            "state": "PASS",
            "read_only": True,
            "verification_ready": True,
            "station_id": "05480",
            "location_id": "station_05480",
            "truth_revision_set_sha256": "d" * 64,
        },
        window={"start": "2026-09-01", "end": "2026-09-30"},
        provider_models=[
            {"provider": "icon_d2", "model_name": "ICON-D2", "model_version": "2026-09"}
        ],
        lead_filters={"lead_buckets": ["0-6h"]},
        sample_filters=sample_filters,
        metric_configuration={"deterministic": ["mae", "rmse", "bias"]},
        sample_evidence=binding["sample_evidence"],
        metric_eligibility={
            "deterministic": ["mae", "rmse", "bias"],
            "ensemble_members": [],
            "weathernext_summary_quantiles": [],
        },
        human_readable_reference="reports/2026-09-watermark.md",
    )


def test_report_lineage_declares_exact_cutoff_and_watermark_identity() -> None:
    watermark = _watermark(later=False)
    receipt = _receipt(watermark)

    filters = receipt["configuration"]["sample_filters"]
    assert filters["watermark_contract"] == "verification-data-watermark-v1"
    assert filters["as_of_utc"] == "2026-09-30T23:59:00Z"
    assert filters["watermark_identity_sha256"] == watermark["watermark_identity_sha256"]
    assert receipt["sample_evidence"]["common_sample_identity_sha256"] == watermark["matched_set_identity_sha256"]


def test_later_watermark_changes_report_lineage_identity() -> None:
    early = _watermark(later=False)
    later = _watermark(later=True)

    early_receipt = _receipt(early)
    later_receipt = _receipt(later)

    assert early["watermark_identity_sha256"] != later["watermark_identity_sha256"]
    assert early_receipt["lineage_identity_sha256"] != later_receipt["lineage_identity_sha256"]
