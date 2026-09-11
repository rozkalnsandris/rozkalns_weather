from datetime import datetime, timedelta, timezone

import pytest

from rozkalns_weather.orchestrator import IngestOrchestrator
from rozkalns_weather.provider_health import classify_public_provider_health


NOW = datetime(2026, 9, 11, 18, tzinfo=timezone.utc)


def _iso(delta: timedelta) -> str:
    return (NOW + delta).isoformat().replace("+00:00", "Z")


class _Settings:
    ingest_timeout_seconds = 1.0
    ingest_retries = 1


class _FailingWriteDatabase:
    def insert_forecast_run(self, run, *, location_id: str) -> int:
        raise RuntimeError("local write failed")


def test_fresh_provider_is_fresh() -> None:
    result = classify_public_provider_health(
        "icon_d2",
        {"state": "ok", "last_attempt_at_utc": _iso(timedelta(minutes=-20)), "last_success_at_utc": _iso(timedelta(minutes=-20))},
        {"last_init_time_utc": _iso(timedelta(hours=-1)), "last_retrieved_at_utc": _iso(timedelta(minutes=-20)), "latest_valid_time_utc": _iso(timedelta(hours=47))},
        now=NOW,
    )
    assert result["freshness_state"] == "fresh"
    assert result["failure_domain"] == "none"
    assert result["reason_code"] == "FRESH"


def test_recent_error_is_upstream_or_transport() -> None:
    result = classify_public_provider_health(
        "ecmwf_ifs",
        {
            "state": "error",
            "last_attempt_at_utc": _iso(timedelta(minutes=-10)),
            "last_success_at_utc": _iso(timedelta(hours=-1)),
            "detail": "upstream_or_transport:forecast_fetch:HTTPStatusError",
        },
        {"last_init_time_utc": _iso(timedelta(hours=-6))},
        now=NOW,
    )
    assert result["freshness_state"] == "error"
    assert result["failure_domain"] == "upstream_or_transport"
    assert result["reason_code"] == "RECENT_UPSTREAM_OR_TRANSPORT_ERROR"


def test_recent_local_persistence_error_is_not_reported_as_upstream() -> None:
    result = classify_public_provider_health(
        "icon_d2",
        {
            "state": "error",
            "last_attempt_at_utc": _iso(timedelta(minutes=-10)),
            "last_success_at_utc": _iso(timedelta(hours=-1)),
            "detail": "station_10416:local_persistence:forecast_write:RuntimeError",
        },
        {"last_init_time_utc": _iso(timedelta(hours=-1))},
        now=NOW,
    )
    assert result["freshness_state"] == "error"
    assert result["failure_domain"] == "local_persistence"
    assert result["reason_code"] == "RECENT_LOCAL_PERSISTENCE_ERROR"


def test_unclassified_recent_error_does_not_guess_upstream() -> None:
    result = classify_public_provider_health(
        "ecmwf_aifs",
        {
            "state": "error",
            "last_attempt_at_utc": _iso(timedelta(minutes=-10)),
            "last_success_at_utc": _iso(timedelta(hours=-1)),
            "detail": "LegacyError",
        },
        {"last_init_time_utc": _iso(timedelta(hours=-1))},
        now=NOW,
    )
    assert result["failure_domain"] == "unknown_ingest_error"
    assert result["reason_code"] == "RECENT_INGEST_ERROR_UNCLASSIFIED"


def test_forecast_write_failure_is_marked_local_persistence() -> None:
    orchestrator = IngestOrchestrator(_Settings(), _FailingWriteDatabase(), sleeper=lambda _: None)
    run = object()
    stored, attempts, detail = orchestrator._record_one_forecast(
        "icon_d2",
        lambda: run,
        NOW,
        location_id="station_10416",
    )
    assert stored is None
    assert attempts == 1
    assert detail == "local_persistence:forecast_write:RuntimeError"


def test_forecast_fetch_failure_is_marked_upstream_or_transport() -> None:
    orchestrator = IngestOrchestrator(_Settings(), _FailingWriteDatabase(), sleeper=lambda _: None)

    def fail_fetch():
        raise TimeoutError("upstream timeout")

    stored, attempts, detail = orchestrator._record_one_forecast(
        "icon_d2",
        fail_fetch,
        NOW,
        location_id="station_10416",
    )
    assert stored is None
    assert attempts == 1
    assert detail == "upstream_or_transport:forecast_fetch:TimeoutError"


def test_stale_attempt_is_local_scheduler_or_ingest() -> None:
    result = classify_public_provider_health(
        "ecmwf_aifs",
        {"state": "ok", "last_attempt_at_utc": _iso(timedelta(hours=-3)), "last_success_at_utc": _iso(timedelta(hours=-3))},
        {"last_init_time_utc": _iso(timedelta(hours=-2))},
        now=NOW,
    )
    assert result["freshness_state"] == "stale"
    assert result["failure_domain"] == "local_scheduler_or_ingest"
    assert result["reason_code"] == "INGEST_ATTEMPT_STALE"


def test_observation_source_age_is_used() -> None:
    result = classify_public_provider_health(
        "dwd_observations",
        {"state": "ok", "last_attempt_at_utc": _iso(timedelta(minutes=-20)), "last_success_at_utc": _iso(timedelta(minutes=-20))},
        {"last_observed_at_utc": _iso(timedelta(hours=-3))},
        now=NOW,
    )
    assert result["freshness_state"] == "lagging"
    assert result["failure_domain"] == "upstream_data"


def test_partial_provider_is_degraded_without_hiding_other_providers() -> None:
    partial = classify_public_provider_health(
        "dwd_mosmix_l",
        {
            "state": "partial",
            "last_attempt_at_utc": _iso(timedelta(minutes=-10)),
            "last_success_at_utc": _iso(timedelta(minutes=-10)),
            "detail": "home:upstream_or_transport:forecast_fetch:TimeoutError",
        },
        {"last_init_time_utc": _iso(timedelta(hours=-1))},
        now=NOW,
    )
    fresh = classify_public_provider_health(
        "icon_d2",
        {"state": "ok", "last_attempt_at_utc": _iso(timedelta(minutes=-10)), "last_success_at_utc": _iso(timedelta(minutes=-10))},
        {"last_init_time_utc": _iso(timedelta(hours=-1))},
        now=NOW,
    )
    assert partial["freshness_state"] == "degraded"
    assert partial["failure_domain"] == "upstream_or_transport"
    assert fresh["freshness_state"] == "fresh"


def test_untracked_provider_is_rejected_by_public_classifier() -> None:
    with pytest.raises(ValueError, match="not in public recurring health scope"):
        classify_public_provider_health("weathernext3", {}, {}, now=NOW)
