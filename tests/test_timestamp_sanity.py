from __future__ import annotations

from rozkalns_weather.provider_latency import provider_health_latency_summary, provider_latency_report
from rozkalns_weather.timestamp_sanity import (
    TIMESTAMP_SANITY_CONTRACT,
    provider_health_timestamp_sanity_summary,
    provider_timestamp_sanity_report,
    timestamp_sanity_sample,
)


def _forecast(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "provider": "icon_d2",
        "model_name": "ICON-D2",
        "init_time_utc": "2026-09-25T00:00:00Z",
        "expected_available_at_utc": "2026-09-25T01:00:00Z",
        "upstream_available_at_utc": "2026-09-25T01:08:00Z",
        "ingest_attempt_at_utc": "2026-09-25T01:10:00Z",
        "retrieved_at_utc": "2026-09-25T01:12:00Z",
        "valid_time_utc": "2026-09-25T06:00:00Z",
    }
    row.update(overrides)
    return row


def _latency_row(**overrides: object) -> dict[str, object]:
    row = _forecast(
        model_version=None,
        run_cycle="00Z",
        expected_availability_source="documented_provider_target",
        upstream_availability_source="open_meteo_model_metadata",
    )
    row.update(overrides)
    return row


def _clock(offset_seconds: float = 0.0) -> dict[str, object]:
    return {
        "measured_at_utc": "2026-09-25T01:15:00Z",
        "offset_seconds": offset_seconds,
    }


def test_normal_timing_is_pass_with_explicit_reference_and_runtime_clock_evidence() -> None:
    result = timestamp_sanity_sample(
        _forecast(),
        reference_time_utc="2026-09-25T01:15:00Z",
        runtime_clock_evidence=_clock(),
    )
    assert result["contract"] == TIMESTAMP_SANITY_CONTRACT
    assert result["state"] == "PASS"
    assert result["reason_codes"] == ["TIMESTAMP_SANITY_OK"]
    assert result["lead_time_hours"] == 6.0
    assert result["reference_clock"]["state"] == "EXPLICIT"
    assert result["runtime_clock"]["state"] == "PASS"
    assert result["clock_skew"] == {
        "provider_evidence": "NOT_DETECTED",
        "local_evidence": "NOT_DETECTED",
    }
    assert result["scheduler_delay_inferred"] is False
    assert result["provider_outage_claimed"] is False


def test_provider_clock_skew_evidence_is_distinct_from_scheduler_delay() -> None:
    result = timestamp_sanity_sample(
        _forecast(upstream_available_at_utc="2026-09-25T01:20:00Z"),
        reference_time_utc="2026-09-25T01:15:00Z",
        runtime_clock_evidence=_clock(),
    )
    assert result["state"] == "BLOCKED"
    assert "UPSTREAM_AVAILABILITY_AFTER_RETRIEVAL" in result["reason_codes"]
    assert "UPSTREAM_AVAILABILITY_FUTURE_BEYOND_TOLERANCE" in result["reason_codes"]
    assert result["clock_skew"]["provider_evidence"] == "SUSPECT"
    assert result["clock_skew"]["local_evidence"] == "NOT_DETECTED"
    assert result["scheduler_delay_inferred"] is False


def test_explicit_local_clock_skew_evidence_warns_without_claiming_provider_outage() -> None:
    result = timestamp_sanity_sample(
        _forecast(),
        reference_time_utc="2026-09-25T01:15:00Z",
        runtime_clock_evidence=_clock(180.0),
    )
    assert result["state"] == "WARN"
    assert result["reason_codes"] == ["LOCAL_CLOCK_SKEW_EVIDENCE"]
    assert result["clock_skew"]["provider_evidence"] == "NOT_DETECTED"
    assert result["clock_skew"]["local_evidence"] == "SUSPECT"
    assert result["provider_outage_claimed"] is False


def test_timestamp_inversion_fails_closed_with_specific_reason() -> None:
    result = timestamp_sanity_sample(
        _forecast(ingest_attempt_at_utc="2026-09-25T01:13:00Z"),
        reference_time_utc="2026-09-25T01:15:00Z",
        runtime_clock_evidence=_clock(),
    )
    assert result["state"] == "BLOCKED"
    assert result["reason_codes"] == ["INGEST_ATTEMPT_AFTER_RETRIEVAL"]


def test_timezone_naive_timestamp_fails_closed() -> None:
    result = timestamp_sanity_sample(
        _forecast(retrieved_at_utc="2026-09-25T01:12:00"),
        reference_time_utc="2026-09-25T01:15:00Z",
        runtime_clock_evidence=_clock(),
    )
    assert result["state"] == "BLOCKED"
    assert result["reason_codes"] == ["TIMESTAMP_TIMEZONE_NAIVE"]


def test_missing_observed_publication_and_runtime_clock_evidence_are_explicit() -> None:
    result = timestamp_sanity_sample(
        _forecast(upstream_available_at_utc=None),
        reference_time_utc="2026-09-25T01:15:00Z",
    )
    assert result["state"] == "WARN"
    assert result["reason_codes"] == ["UPSTREAM_AVAILABILITY_UNOBSERVED"]
    assert result["availability_semantics"]["upstream_is_observed_evidence"] is False
    assert result["availability_semantics"]["upstream_timestamp_fabricated"] is False
    assert result["runtime_clock"] == {
        "state": "UNKNOWN",
        "reason_code": "RUNTIME_CLOCK_EVIDENCE_UNAVAILABLE",
        "offset_seconds": None,
        "measured_at_utc": None,
    }
    assert result["clock_skew"]["local_evidence"] == "UNKNOWN"


def test_future_retrieval_beyond_tolerance_fails_closed() -> None:
    result = timestamp_sanity_sample(
        _forecast(
            ingest_attempt_at_utc="2026-09-25T01:20:00Z",
            retrieved_at_utc="2026-09-25T01:21:00Z",
        ),
        reference_time_utc="2026-09-25T01:15:00Z",
        runtime_clock_evidence=_clock(),
    )
    assert result["state"] == "BLOCKED"
    assert "RETRIEVAL_FUTURE_BEYOND_TOLERANCE" in result["reason_codes"]
    assert "INGEST_ATTEMPT_FUTURE_BEYOND_TOLERANCE" not in result["reason_codes"]


def test_negative_lead_time_fails_closed() -> None:
    result = timestamp_sanity_sample(
        _forecast(valid_time_utc="2026-09-24T23:00:00Z"),
        reference_time_utc="2026-09-25T01:15:00Z",
        runtime_clock_evidence=_clock(),
    )
    assert result["state"] == "BLOCKED"
    assert result["reason_codes"] == ["NEGATIVE_LEAD_TIME"]
    assert result["lead_time_hours"] == -1.0


def test_future_observation_is_checked_without_fabricating_publication_time() -> None:
    result = timestamp_sanity_sample(
        {
            "provider": "dwd_observations",
            "model_name": "DWD CDC observation",
            "observation_time_utc": "2026-09-25T01:30:00Z",
            "ingest_attempt_at_utc": "2026-09-25T01:10:00Z",
            "retrieved_at_utc": "2026-09-25T01:12:00Z",
        },
        reference_time_utc="2026-09-25T01:15:00Z",
        runtime_clock_evidence=_clock(),
    )
    assert result["state"] == "BLOCKED"
    assert "OBSERVATION_AFTER_RETRIEVAL" in result["reason_codes"]
    assert "OBSERVATION_FUTURE_BEYOND_TOLERANCE" in result["reason_codes"]
    assert result["availability_semantics"]["upstream_timestamp_fabricated"] is False


def test_report_and_provider_health_summary_remain_read_only_and_provider_scoped() -> None:
    report = provider_timestamp_sanity_report(
        [_forecast(), _forecast(provider="ecmwf_ifs", model_name="IFS HRES")],
        reference_time_utc="2026-09-25T01:15:00Z",
        runtime_clock_evidence=_clock(),
    )
    icon = provider_health_timestamp_sanity_summary(report, "icon_d2")
    assert report["state"] == "PASS"
    assert report["summary"]["samples"] == 2
    assert icon["state"] == "PASS"
    assert len(icon["samples"]) == 1
    assert icon["affects_provider_freshness_state"] is False
    assert icon["provider_outage_claimed"] is False


def test_latency_report_exposes_timestamp_sanity_without_rewriting_latency_semantics() -> None:
    report = provider_latency_report(
        [_latency_row()],
        reference_time_utc="2026-09-25T01:15:00Z",
        runtime_clock_evidence=_clock(),
    )
    assert report["state"] == "PASS"
    assert report["reason_codes"] == ["LATENCY_WITHIN_BOUNDS"]
    assert report["timestamp_sanity"]["state"] == "PASS"

    health = provider_health_latency_summary(report, "icon_d2")
    assert health["state"] == "PASS"
    assert health["timestamp_sanity"]["state"] == "PASS"
    assert health["timestamp_sanity"]["affects_provider_freshness_state"] is False
