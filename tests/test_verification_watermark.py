from __future__ import annotations

import json
from pathlib import Path

import pytest

from rozkalns_weather.verification_watermark import (
    VerificationWatermarkError,
    build_verification_watermark,
    validate_verification_watermark,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "verification_watermark_cases.json"
CONTRACT_PATH = Path(__file__).parents[1] / "contracts" / "verification-data-watermark-v1.json"


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _build(*, later: bool = False, latency_report: dict[str, object] | None = None) -> dict[str, object]:
    fixture = _fixture()
    cutoff = fixture["later_cutoff"] if later else fixture["cutoff"]
    return build_verification_watermark(
        fixture["samples"],
        as_of_utc=cutoff,
        report_generated_at_utc=fixture["report_generated_at"],
        latency_report=latency_report,
    )


def _sample(report: dict[str, object], sample_id: str) -> dict[str, object]:
    return next(item for item in report["samples"] if item["sample_id"] == sample_id)


def test_cutoff_is_deterministic_and_reason_codes_are_explicit() -> None:
    first = _build()
    second = _build()

    assert first == second
    assert first["contract"] == "verification-data-watermark-v1"
    assert first["schema_version"] == 1
    assert first["as_of_utc"] == "2026-09-30T23:59:00Z"
    assert first["read_only"] is True
    assert len(first["watermark_identity_sha256"]) == 64
    assert len(first["matched_set_identity_sha256"]) == 64

    assert _sample(first, "on-time")["reason_codes"] == ["ON_TIME"]
    assert "LATE_FORECAST_RETRIEVAL" in _sample(first, "late-forecast")["reason_codes"]
    assert "LATE_TRUTH_ARRIVAL" in _sample(first, "late-truth-month-boundary")["reason_codes"]
    assert "POST_CUTOFF_TRUTH_REVISION" in _sample(first, "post-cutoff-revision")["reason_codes"]
    assert set(_sample(first, "genuinely-missing")["reason_codes"]) == {"FORECAST_MISSING", "TRUTH_MISSING"}

    validation = validate_verification_watermark(first)
    assert validation["state"] == "PASS"
    assert validation["watermark_identity_sha256"] == first["watermark_identity_sha256"]


def test_later_watermark_admits_late_data_without_rewriting_prior_evidence() -> None:
    early = _build()
    later = _build(later=True)

    assert early["watermark_identity_sha256"] != later["watermark_identity_sha256"]
    assert early["matched_set_identity_sha256"] != later["matched_set_identity_sha256"]
    assert "late-forecast" not in early["eligible_sample_ids"]
    assert "late-truth-month-boundary" not in early["eligible_sample_ids"]
    assert "late-forecast" in later["eligible_sample_ids"]
    assert "late-truth-month-boundary" in later["eligible_sample_ids"]

    early_revision = _sample(early, "post-cutoff-revision")
    later_revision = _sample(later, "post-cutoff-revision")
    assert early_revision["selected_truth_revision_identity_sha256"] == "4" * 64
    assert later_revision["selected_truth_revision_identity_sha256"] == "5" * 64
    assert early_revision["post_cutoff_truth_revision_present"] is True
    assert later_revision["post_cutoff_truth_revision_present"] is False
    assert early["history_policy"]["corpus_history_mutated"] is False
    assert early["history_policy"]["late_data_deleted"] is False


def test_latency_context_is_bound_but_never_invents_availability() -> None:
    latency = {
        "contract": "provider-availability-latency-v1",
        "state": "WARN",
        "reason_codes": ["RETRIEVAL_LATE", "UPSTREAM_AVAILABILITY_UNOBSERVED"],
    }
    report = _build(latency_report=latency)

    assert report["latency_context"] == {
        "contract": "provider-availability-latency-v1",
        "state": "WARN",
        "reason_codes": ["RETRIEVAL_LATE", "UPSTREAM_AVAILABILITY_UNOBSERVED"],
        "affects_cutoff_selection": False,
    }
    assert report["history_policy"]["availability_timestamps_fabricated"] is False


def test_invalid_latency_contract_and_report_time_fail_closed() -> None:
    with pytest.raises(VerificationWatermarkError) as latency_error:
        _build(latency_report={"contract": "other-v1"})
    assert latency_error.value.reason_code == "LATENCY_CONTRACT_MISMATCH"

    fixture = _fixture()
    with pytest.raises(VerificationWatermarkError) as time_error:
        build_verification_watermark(
            fixture["samples"],
            as_of_utc=fixture["cutoff"],
            report_generated_at_utc="2026-09-30T20:00:00Z",
        )
    assert time_error.value.reason_code == "REPORT_GENERATED_BEFORE_WATERMARK"


def test_machine_contract_matches_python_contract_and_privacy_boundary() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    report = _build()

    assert contract["contract"] == report["contract"]
    assert contract["schema_version"] == report["schema_version"]
    assert set(contract["stable_reason_codes"]) == {
        "ON_TIME",
        "LATE_FORECAST_RETRIEVAL",
        "LATE_TRUTH_ARRIVAL",
        "POST_CUTOFF_TRUTH_REVISION",
        "FORECAST_MISSING",
        "TRUTH_MISSING",
    }
    assert report["privacy"] == {
        "coordinates_exposed": False,
        "credentials_exposed": False,
        "database_path_exposed": False,
        "raw_logs_exposed": False,
    }
