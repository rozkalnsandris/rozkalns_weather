from __future__ import annotations

import json

import pytest

from rozkalns_weather.verification_missingness import (
    ATTRITION_IMBALANCE_BLOCKED,
    ATTRITION_IMBALANCE_WARN,
    AUDIT_CONTRACT,
    BLOCKED,
    WARN,
    MATCHED,
    PEER_COMMON_SAMPLE_EXCLUDED,
    SEMANTIC_INCOMPATIBILITY,
    TRUTH_GAP,
    UPSTREAM_FORECAST_MISSING,
    VERIFICATION_FILTER_EXCLUDED,
    ExpectedVerificationSample,
    MissingnessAuditError,
    build_verification_missingness_report,
)


def sample(
    sample_id: str,
    provider: str,
    model_version: str,
    *,
    lead_hours: float = 12.0,
    valid_time_utc: str = "2026-05-02T12:00:00Z",
    init_time_utc: str = "2026-05-02T00:00:00Z",
    forecast_available: bool = True,
    truth_available: bool = True,
    semantic_compatible: bool = True,
    verification_included: bool = True,
) -> ExpectedVerificationSample:
    return ExpectedVerificationSample(
        sample_id=sample_id,
        provider=provider,
        model_version=model_version,
        lead_hours=lead_hours,
        variable="temperature_2m",
        valid_time_utc=valid_time_utc,
        init_time_utc=init_time_utc,
        forecast_available=forecast_available,
        truth_available=truth_available,
        semantic_compatible=semantic_compatible,
        verification_included=verification_included,
    )


def pair(
    sample_id: str,
    *,
    icon_version: str = "icon-v1",
    ifs_version: str = "ifs-v1",
    **kwargs: object,
) -> list[ExpectedVerificationSample]:
    return [
        sample(sample_id, "icon_d2", icon_version, **kwargs),
        sample(sample_id, "ecmwf_ifs", ifs_version, **kwargs),
    ]


def comparison(report: dict[str, object], index: int = 0) -> dict[str, object]:
    comparisons = report["comparisons"]
    assert isinstance(comparisons, list)
    item = comparisons[index]
    assert isinstance(item, dict)
    return item


def providers_by_name(item: dict[str, object]) -> dict[str, dict[str, object]]:
    providers = item["providers"]
    assert isinstance(providers, list)
    return {str(row["provider"]): row for row in providers}


def test_complete_matched_samples_are_pass_and_byte_stable() -> None:
    rows = [
        *pair("a"),
        *pair(
            "b",
            valid_time_utc="2026-05-02T18:00:00Z",
            init_time_utc="2026-05-02T06:00:00Z",
        ),
    ]
    report_a = build_verification_missingness_report(rows)
    report_b = build_verification_missingness_report(reversed(rows))

    assert report_a == report_b
    assert report_a["contract"] == AUDIT_CONTRACT
    assert report_a["state"] == "PASS"
    assert report_a["automatic_weighting"] is False
    assert "winner" not in report_a
    assert json.dumps(report_a, sort_keys=True)

    first = comparison(report_a, 0)
    assert first["month"] == "2026-05"
    assert first["init_cycle"] == "00Z"
    assert first["lead_bucket"] == "12-24h"
    assert first["matched_n"] == 1
    assert len(str(first["matched_set_id"])) == 64
    by_provider = providers_by_name(first)
    assert by_provider["icon_d2"]["expected_n"] == 1
    assert by_provider["icon_d2"]["available_n"] == 1
    assert by_provider["icon_d2"]["matched_n"] == 1
    assert by_provider["icon_d2"]["excluded_n"] == 0
    assert by_provider["icon_d2"]["reason_counts"][MATCHED] == 1


def test_asymmetric_provider_gap_is_blocked_at_material_threshold() -> None:
    rows: list[ExpectedVerificationSample] = []
    for index in range(4):
        valid = f"2026-05-03T{12 + index:02d}:00:00Z"
        rows.append(
            sample(
                f"s{index}",
                "icon_d2",
                "icon-v1",
                valid_time_utc=valid,
            )
        )
        rows.append(
            sample(
                f"s{index}",
                "ecmwf_ifs",
                "ifs-v1",
                valid_time_utc=valid,
                forecast_available=index != 3,
            )
        )

    report = build_verification_missingness_report(rows)
    item = comparison(report)
    assert item["state"] == BLOCKED
    assert item["state_reason_codes"] == [ATTRITION_IMBALANCE_BLOCKED]
    assert item["imbalance_fraction"] == 0.25
    by_provider = providers_by_name(item)
    assert by_provider["ecmwf_ifs"]["available_n"] == 3
    assert by_provider["ecmwf_ifs"]["matched_n"] == 3
    assert by_provider["ecmwf_ifs"]["excluded_n"] == 1
    assert by_provider["ecmwf_ifs"]["reason_counts"][UPSTREAM_FORECAST_MISSING] == 1
    assert by_provider["icon_d2"]["reason_counts"][PEER_COMMON_SAMPLE_EXCLUDED] == 1


def test_moderate_provider_gap_emits_warn_threshold() -> None:
    rows: list[ExpectedVerificationSample] = []
    for index in range(5):
        valid = f"2026-05-04T{12 + index:02d}:00:00Z"
        rows.append(
            sample(
                f"w{index}",
                "icon_d2",
                "icon-v1",
                valid_time_utc=valid,
            )
        )
        rows.append(
            sample(
                f"w{index}",
                "ecmwf_ifs",
                "ifs-v1",
                valid_time_utc=valid,
                forecast_available=index != 4,
            )
        )
    item = comparison(build_verification_missingness_report(rows))
    assert item["state"] == WARN
    assert item["state_reason_codes"] == [ATTRITION_IMBALANCE_WARN]
    assert item["imbalance_fraction"] == pytest.approx(0.2)


def test_truth_semantic_and_filter_exclusions_are_separate_reason_codes() -> None:
    rows = [
        sample("truth", "icon_d2", "icon-v1", truth_available=False),
        sample("truth", "ecmwf_ifs", "ifs-v1", truth_available=False),
        sample(
            "semantic",
            "icon_d2",
            "icon-v1",
            valid_time_utc="2026-05-02T13:00:00Z",
            semantic_compatible=False,
        ),
        sample(
            "semantic",
            "ecmwf_ifs",
            "ifs-v1",
            valid_time_utc="2026-05-02T13:00:00Z",
            semantic_compatible=False,
        ),
        sample(
            "filter",
            "icon_d2",
            "icon-v1",
            valid_time_utc="2026-05-02T14:00:00Z",
            verification_included=False,
        ),
        sample(
            "filter",
            "ecmwf_ifs",
            "ifs-v1",
            valid_time_utc="2026-05-02T14:00:00Z",
            verification_included=False,
        ),
        *pair("matched", valid_time_utc="2026-05-02T15:00:00Z"),
    ]

    report = build_verification_missingness_report(rows)
    item = comparison(report)
    assert item["state"] == "PASS"
    assert item["matched_sample_ids"] == ["matched"]
    by_provider = providers_by_name(item)
    reasons = by_provider["icon_d2"]["reason_counts"]
    assert reasons[TRUTH_GAP] == 1
    assert reasons[SEMANTIC_INCOMPATIBILITY] == 1
    assert reasons[VERIFICATION_FILTER_EXCLUDED] == 1
    assert by_provider["icon_d2"]["excluded_n"] == 3


def test_sparse_long_lead_is_audited_without_imputation() -> None:
    report = build_verification_missingness_report(
        pair(
            "long",
            lead_hours=180.0,
            valid_time_utc="2026-05-09T12:00:00Z",
            init_time_utc="2026-05-02T00:00:00Z",
        )
    )
    item = comparison(report)
    assert item["lead_bucket"] == "7-10d"
    assert item["expected_n"] == 1
    assert item["matched_n"] == 1
    assert item["matched_sample_ids"] == ["long"]


def test_model_version_boundaries_create_distinct_comparison_cohorts() -> None:
    rows = [
        *pair("old", icon_version="icon-old"),
        *pair(
            "new",
            icon_version="icon-new",
            valid_time_utc="2026-05-02T13:00:00Z",
        ),
    ]
    report = build_verification_missingness_report(rows)
    comparisons = report["comparisons"]
    assert isinstance(comparisons, list)
    assert len(comparisons) == 2
    assert {
        tuple(sorted(item["comparison_cohort"].items()))
        for item in comparisons
    } == {
        (("ecmwf_ifs", "ifs-v1"), ("icon_d2", "icon-old")),
        (("ecmwf_ifs", "ifs-v1"), ("icon_d2", "icon-new")),
    }
    assert len({item["matched_set_id"] for item in comparisons}) == 2


def test_incomplete_expected_matrix_fails_closed_instead_of_inventing_reason() -> None:
    with pytest.raises(MissingnessAuditError) as exc:
        build_verification_missingness_report(
            [sample("a", "icon_d2", "icon-v1")],
            expected_providers=("icon_d2", "ecmwf_ifs"),
        )
    assert exc.value.reason_code == "INCOMPLETE_EXPECTED_MATRIX"


def test_multiple_direct_failures_keep_deterministic_primary_reason_and_full_evidence() -> None:
    rows = [
        sample(
            "a",
            "icon_d2",
            "icon-v1",
            forecast_available=False,
            truth_available=False,
        ),
        sample("a", "ecmwf_ifs", "ifs-v1"),
    ]
    report = build_verification_missingness_report(rows)
    item = comparison(report)
    by_provider = providers_by_name(item)
    icon = by_provider["icon_d2"]
    assert icon["reason_counts"][UPSTREAM_FORECAST_MISSING] == 1
    assert icon["direct_reason_codes_by_sample"]["a"] == [
        UPSTREAM_FORECAST_MISSING,
        TRUTH_GAP,
    ]
