from datetime import datetime, timedelta, timezone

import pytest

from rozkalns_weather.models import Observation
from rozkalns_weather.orchestrator import IngestOrchestrator
from rozkalns_weather.provider_health import classify_public_provider_health
from rozkalns_weather.providers.dwd_current_observations import CURRENT_MODEL_NAME, CURRENT_SOURCE_PROVIDER

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
        self.inserted = []
        self.status = None

    def insert_observations(self, observations):
        self.inserted.extend(observations)
        return len(observations)

    def set_provider_status(self, provider, **kwargs):
        self.status = {"provider": provider, **kwargs}


def test_public_model_freshness() -> None:
    result = classify_public_provider_health(
        "icon_d2",
        {"state": "ok", "last_attempt_at_utc": _iso(timedelta(minutes=-20)), "last_success_at_utc": _iso(timedelta(minutes=-20))},
        {"last_init_time_utc": _iso(timedelta(hours=-1))},
        now=NOW,
    )
    assert result["freshness_state"] == "fresh"
    assert result["reason_code"] == "FRESH"


def test_provider_failure_domains_remain_visible() -> None:
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


def test_local_write_failure_is_not_reported_as_upstream() -> None:
    orchestrator = IngestOrchestrator(_Settings(), _FailingWriteDatabase(), sleeper=lambda _: None)
    stored, attempts, detail = orchestrator._record_one_forecast(
        "icon_d2", lambda: object(), NOW, location_id="station_05480"
    )
    assert stored is None
    assert attempts == 1
    assert detail == "local_persistence:forecast_write:RuntimeError"


def test_current_observation_source_time_is_preserved() -> None:
    database = _ObservationDatabase()
    orchestrator = IngestOrchestrator(_Settings(), database, sleeper=lambda _: None)
    observation = Observation(
        source_provider=CURRENT_SOURCE_PROVIDER,
        station_id="05480",
        location_id="station_05480",
        observed_at_utc=NOW - timedelta(hours=1),
        variable="temperature_2m",
        value=11.0,
        unit="degC",
    )
    outcome = orchestrator._record_observations(
        "dwd_observations", lambda: [observation], NOW,
        location_id="station_05480", model_name=CURRENT_MODEL_NAME,
    )
    assert outcome.state == "ok"
    assert database.status["init_time"] == NOW - timedelta(hours=1)


def test_weather_next_is_not_in_recurring_public_health_scope() -> None:
    with pytest.raises(ValueError, match="not in public recurring health scope"):
        classify_public_provider_health("weathernext3", {}, {}, now=NOW)
