from __future__ import annotations

from rozkalns_weather.provider_health import classify_public_provider_health
from rozkalns_weather.provider_latency import (
    LATENCY_CONTRACT,
    provider_health_latency_summary,
    provider_latency_report,
)


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "provider": "icon_d2",
        "model_name": "ICON-D2",
        "model_version": None,
        "run_cycle": "00Z",
        "init_time_utc": "2026-09-16T00:00:00Z",
        "expected_available_at_utc": "2026-09-16T01:00:00Z",
        "expected_availability_source": "documented_provider_target",
        "upstream_available_at_utc": "2026-09-16T01:10:00Z",
        "upstream_availability_source": "open_meteo_model_metadata",
        "ingest_attempt_at_utc": "2026-09-16T01:15:00Z",
        "retrieved_at_utc": "2026-09-16T01:18:00Z",
    }
    row.update(overrides)
    return row


def test_normal_latency_is_pass_and_preserves_provenance() -> None:
    report = provider_latency_report([_row()])

    assert report["contract"] == LATENCY_CONTRACT
    assert report["state"] == "PASS"
    assert report["reason_codes"] == ["LATENCY_WITHIN_BOUNDS"]
    sample = report["samples"][0]
    assert sample["expected_available_at_utc"] == "2026-09-16T01:00:00Z"
    assert sample["upstream_available_at_utc"] == "2026-09-16T01:10:00Z"
    assert sample["provenance"]["upstream_is_observed_evidence"] is True
    assert sample["provenance"]["upstream_timestamp_fabricated"] is False
    assert sample["outage_claimed"] is False


def test_delayed_upstream_availability_is_warn_not_outage() -> None:
    report = provider_latency_report([
        _row(
            upstream_available_at_utc="2026-09-16T01:45:00Z",
            ingest_attempt_at_utc="2026-09-16T01:50:00Z",
            retrieved_at_utc="2026-09-16T01:55:00Z",
        )
    ])

    assert report["state"] == "WARN"
    assert "UPSTREAM_AVAILABILITY_LATE" in report["reason_codes"]
    assert "RETRIEVAL_LATE" not in report["reason_codes"]
    assert report["health_integration"]["outage_claimed"] is False


def test_delayed_local_retrieval_attempt_is_distinct_from_upstream_delay() -> None:
    report = provider_latency_report([
        _row(
            upstream_available_at_utc="2026-09-16T01:05:00Z",
            ingest_attempt_at_utc="2026-09-16T01:50:00Z",
            retrieved_at_utc="2026-09-16T01:55:00Z",
        )
    ])

    assert report["state"] == "WARN"
    assert "LOCAL_RETRIEVAL_ATTEMPT_LATE" in report["reason_codes"]
    assert "UPSTREAM_AVAILABILITY_LATE" not in report["reason_codes"]


def test_missing_observed_publication_evidence_is_explicit_and_not_fabricated() -> None:
    report = provider_latency_report([
        _row(
            upstream_available_at_utc=None,
            upstream_availability_source=None,
            ingest_attempt_at_utc="2026-09-16T01:10:00Z",
            retrieved_at_utc="2026-09-16T01:12:00Z",
        )
    ])

    assert report["state"] == "WARN"
    assert report["reason_codes"] == ["UPSTREAM_AVAILABILITY_UNOBSERVED"]
    sample = report["samples"][0]
    assert sample["upstream_available_at_utc"] is None
    assert sample["provenance"]["upstream_is_observed_evidence"] is False
    assert sample["provenance"]["upstream_timestamp_fabricated"] is False


def test_unusually_late_retrieval_has_stable_reason_code() -> None:
    report = provider_latency_report([
        _row(
            ingest_attempt_at_utc="2026-09-16T02:05:00Z",
            retrieved_at_utc="2026-09-16T02:10:00Z",
        )
    ])

    assert report["state"] == "WARN"
    assert "RETRIEVAL_LATE" in report["reason_codes"]
    assert "LOCAL_RETRIEVAL_ATTEMPT_LATE" in report["reason_codes"]


def test_timestamp_inversion_fails_closed() -> None:
    report = provider_latency_report([
        _row(
            upstream_available_at_utc="2026-09-16T01:30:00Z",
            ingest_attempt_at_utc="2026-09-16T01:20:00Z",
            retrieved_at_utc="2026-09-16T01:25:00Z",
        )
    ])

    assert report["state"] == "BLOCKED"
    assert report["reason_codes"] == ["TIMESTAMP_ORDER_INVALID"]
    assert report["samples"] == []


def test_group_distributions_are_by_provider_model_and_run_cycle() -> None:
    report = provider_latency_report([
        _row(retrieved_at_utc="2026-09-16T01:18:00Z"),
        _row(
            init_time_utc="2026-09-16T12:00:00Z",
            expected_available_at_utc="2026-09-16T13:00:00Z",
            upstream_available_at_utc="2026-09-16T13:08:00Z",
            ingest_attempt_at_utc="2026-09-16T13:12:00Z",
            retrieved_at_utc="2026-09-16T13:20:00Z",
            run_cycle="12Z",
        ),
        _row(
            provider="ecmwf_ifs",
            model_name="IFS HRES",
            init_time_utc="2026-09-16T00:00:00Z",
            expected_available_at_utc="2026-09-16T06:00:00Z",
            upstream_available_at_utc=None,
            upstream_availability_source=None,
            ingest_attempt_at_utc="2026-09-16T06:10:00Z",
            retrieved_at_utc="2026-09-16T06:15:00Z",
        ),
    ])

    identities = {(g["provider"], g["model_name"], g["run_cycle"]) for g in report["groups"]}
    assert identities == {
        ("icon_d2", "ICON-D2", "00Z"),
        ("icon_d2", "ICON-D2", "12Z"),
        ("ecmwf_ifs", "IFS HRES", "00Z"),
    }
    icon_group = next(g for g in report["groups"] if g["provider"] == "icon_d2" and g["run_cycle"] == "00Z")
    assert icon_group["distributions"]["expected_to_retrieval"]["n"] == 1


def test_provider_health_integration_does_not_reclassify_freshness_as_outage() -> None:
    report = provider_latency_report([
        _row(
            upstream_available_at_utc=None,
            upstream_availability_source=None,
            retrieved_at_utc="2026-09-16T02:10:00Z",
            ingest_attempt_at_utc="2026-09-16T02:05:00Z",
        )
    ])
    latency = provider_health_latency_summary(report, "icon_d2")
    health = classify_public_provider_health(
        "icon_d2",
        {
            "state": "ok",
            "last_attempt_at_utc": "2026-09-16T02:05:00Z",
            "last_success_at_utc": "2026-09-16T02:10:00Z",
        },
        {
            "last_init_time_utc": "2026-09-16T00:00:00Z",
            "last_retrieved_at_utc": "2026-09-16T02:10:00Z",
            "latest_valid_time_utc": "2026-09-18T00:00:00Z",
        },
        now="2026-09-16T02:15:00Z",  # type: ignore[arg-type]
        latency_summary=latency,
    )

    assert health["freshness_state"] == "fresh"
    assert health["reason_code"] == "FRESH"
    assert health["failure_domain"] == "none"
    assert health["latency_benchmark"]["state"] == "WARN"
    assert health["latency_benchmark"]["outage_claimed"] is False
