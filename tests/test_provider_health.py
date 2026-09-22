from datetime import datetime, timedelta, timezone

import pytest

from rozkalns_weather.models import Observation
from rozkalns_weather.orchestrator import IngestOrchestrator
from rozkalns_weather.provider_health import classify_public_provider_health
from rozkalns_weather.providers.dwd_current_observations import (
    CURRENT_MODEL_NAME,
    CURRENT_SOURCE_PROVIDER,
)


NOW = datetime(2026, 9, 11, 18, tzinfo=timezone.utc)


def _iso(delta: timedelta) -> str:
    return (NOW + delta).isoformat().replace("+00:00", "Z")


class _Settings:
    ingest_timeout_seconds = 1.0
    ingest_retries = 1


class _FailingWriteDatabase:
    def insert_forecast_run(self, run, *, location_id: str) -> int:
        raise RuntimeError("local write failed")


class _ObservationDatabase:
    def __init__(self) -> None:
        self.inserted: list[Observation] = []
        self.status: dict[str, object] | None = None

    def insert_observations(self, observations: list[Observation]) -> int:
        self.inserted.extend(observations)
        return len(observations)

    def set_provider_status(self, provider: str, **kwargs) -> None:
        self.status = {"provider": provider, **kwargs}


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


@pytest.mark.parametrize(
    ("source_age", "freshness_state", "reason_code"),
    [
        (timedelta(hours=-1), "fresh", "FRESH"),
        (timedelta(hours=-3), "lagging", "SOURCE_DATA_LAGGING"),
        (timedelta(hours=-5), "stale", "SOURCE_DATA_STALE"),
    ],
)
def test_dwd_observation_health_uses_canonical_ingest_source_time(
    source_age: timedelta,
    freshness_state: str,
    reason_code: str,
) -> None:
    canonical_time = _iso(source_age)
    result = classify_public_provider_health(
        "dwd_observations",
        {
            "state": "ok",
            "model_name": CURRENT_MODEL_NAME,
            "last_attempt_at_utc": _iso(timedelta(minutes=-20)),
            "last_success_at_utc": _iso(timedelta(minutes=-20)),
            "last_init_time_utc": canonical_time,
        },
        # Generic DB evidence may still describe hourly/legacy DWD truth; measured
        # current health must never silently use it.
        {"last_observed_at_utc": _iso(timedelta(minutes=-5))},
        now=NOW,
    )
    assert result["last_observed_at_utc"] == canonical_time
    assert result["last_init_time_utc"] is None
    assert result["freshness_state"] == freshness_state
    assert result["reason_code"] == reason_code


def test_dwd_legacy_only_evidence_does_not_satisfy_current_health() -> None:
    result = classify_public_provider_health(
        "dwd_observations",
        {
            "state": "ok",
            "last_attempt_at_utc": _iso(timedelta(minutes=-20)),
            "last_success_at_utc": _iso(timedelta(minutes=-20)),
        },
        {"last_observed_at_utc": _iso(timedelta(minutes=-5))},
        now=NOW,
    )
    assert result["last_observed_at_utc"] is None
    assert result["freshness_state"] == "unknown"
    assert result["failure_domain"] == "provenance"
    assert result["reason_code"] == "SOURCE_TIME_MISSING"


def test_pre_cutover_hourly_status_does_not_satisfy_current_health() -> None:
    result = classify_public_provider_health(
        "dwd_observations",
        {
            "state": "ok",
            "model_name": "DWD CDC Observations",
            "last_attempt_at_utc": _iso(timedelta(minutes=-20)),
            "last_success_at_utc": _iso(timedelta(minutes=-20)),
            "last_init_time_utc": _iso(timedelta(minutes=-10)),
        },
        {},
        now=NOW,
    )
    assert result["last_observed_at_utc"] is None
    assert result["freshness_state"] == "unknown"
    assert result["reason_code"] == "SOURCE_TIME_MISSING"


def test_observation_ingest_persists_latest_canonical_source_time() -> None:
    database = _ObservationDatabase()
    orchestrator = IngestOrchestrator(_Settings(), database, sleeper=lambda _: None)
    observations = [
        Observation(
            source_provider=CURRENT_SOURCE_PROVIDER,
            station_id="05480",
            location_id="station_05480",
            observed_at_utc=NOW - timedelta(hours=3),
            variable="temperature_2m",
            value=10.0,
            unit="degC",
        ),
        Observation(
            source_provider=CURRENT_SOURCE_PROVIDER,
            station_id="05480",
            location_id="station_05480",
            observed_at_utc=NOW - timedelta(hours=1),
            variable="temperature_2m",
            value=11.0,
            unit="degC",
        ),
    ]
    outcome = orchestrator._record_observations(
        "dwd_observations",
        lambda: observations,
        NOW,
        location_id="station_05480",
        model_name=CURRENT_MODEL_NAME,
    )
    assert outcome.state == "ok"
    assert database.status is not None
    assert database.status["model_name"] == CURRENT_MODEL_NAME
    assert database.status["init_time"] == NOW - timedelta(hours=1)
    assert database.status["detail"] is None


def test_empty_observation_ingest_does_not_fabricate_source_time() -> None:
    database = _ObservationDatabase()
    orchestrator = IngestOrchestrator(_Settings(), database, sleeper=lambda _: None)
    outcome = orchestrator._record_observations(
        "dwd_observations",
        lambda: [],
        NOW,
        location_id="station_05480",
        model_name=CURRENT_MODEL_NAME,
    )
    assert outcome.state == "ok"
    assert outcome.detail == "no_observations_returned"
    assert database.status is not None
    assert database.status["init_time"] is None
    assert database.status["detail"] == "no_observations_returned"


def test_observation_identity_mismatch_is_upstream_error() -> None:
    database = _ObservationDatabase()
    orchestrator = IngestOrchestrator(_Settings(), database, sleeper=lambda _: None)
    legacy = Observation(
        source_provider="DWD",
        station_id="10416",
        location_id="station_10416",
        observed_at_utc=NOW - timedelta(minutes=10),
        variable="temperature_2m",
        value=10.0,
        unit="degC",
    )
    outcome = orchestrator._record_observations(
        "dwd_observations",
        lambda: [legacy],
        NOW,
        location_id="station_05480",
        model_name=CURRENT_MODEL_NAME,
    )
    assert outcome.state == "error"
    assert outcome.detail == "upstream_or_transport:observation_identity:location_mismatch"
    assert database.inserted == []


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
