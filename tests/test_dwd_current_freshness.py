from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from rozkalns_weather.app import create_app
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database
from rozkalns_weather.locations import DWD_CDC_05480
from rozkalns_weather.models import Observation
from rozkalns_weather.providers.dwd_current_observations import (
    CURRENT_MODEL_NAME,
    CURRENT_SOURCE_PROVIDER,
)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def test_current_and_health_share_canonical_05480_current_feed_time(tmp_path) -> None:
    settings = Settings.from_env({"DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}"})
    database = Database(settings.database_url)
    client = TestClient(create_app(settings=settings, database=database))

    database.ensure_location(
        location_id=DWD_CDC_05480.id,
        label=DWD_CDC_05480.label,
        lat=DWD_CDC_05480.lat,
        lon=DWD_CDC_05480.lon,
        elevation_m=DWD_CDC_05480.elevation_m,
        timezone=DWD_CDC_05480.timezone,
    )

    now = datetime.now(timezone.utc).replace(microsecond=0)
    canonical_time = now - timedelta(hours=1)
    older_current_time = now - timedelta(hours=2)
    newer_hourly_time = now - timedelta(minutes=20)
    legacy_time = now - timedelta(minutes=5)
    database.insert_observations(
        [
            Observation(
                source_provider=CURRENT_SOURCE_PROVIDER,
                station_id="05480",
                location_id="station_05480",
                observed_at_utc=canonical_time,
                variable="temperature_2m",
                value=12.0,
                unit="degC",
            ),
            # A field that exists only at an older current-feed timestamp must not
            # be mixed into the coherent /api/current payload.
            Observation(
                source_provider=CURRENT_SOURCE_PROVIDER,
                station_id="05480",
                location_id="station_05480",
                observed_at_utc=older_current_time,
                variable="wind_speed_10m",
                value=2.0,
                unit="m/s",
            ),
            # Hourly verification truth may be newer or older independently; it
            # must never satisfy the current-now API or provider health.
            Observation(
                source_provider="DWD",
                station_id="05480",
                location_id="station_05480",
                observed_at_utc=newer_hourly_time,
                variable="temperature_2m",
                value=88.0,
                unit="degC",
            ),
            Observation(
                source_provider="DWD",
                station_id="10416",
                location_id="station_10416",
                observed_at_utc=legacy_time,
                variable="temperature_2m",
                value=99.0,
                unit="degC",
            ),
        ]
    )
    database.set_provider_status(
        "dwd_observations",
        state="ok",
        now=now,
        model_name=CURRENT_MODEL_NAME,
        init_time=canonical_time,
    )

    current = client.get("/api/current")
    health = client.get("/api/health/providers")
    assert current.status_code == 200
    assert health.status_code == 200

    current_payload = current.json()
    health_payload = health.json()
    dwd_health = next(item for item in health_payload["providers"] if item["id"] == "dwd_observations")

    assert current_payload["location"]["id"] == "station_05480"
    assert current_payload["location"]["station_id"] == "05480"
    assert current_payload["truth_source"] == "DWD CDC 10-minute 05480"
    assert len(current_payload["observations"]) == 1
    assert current_payload["observations"][0]["source_provider"] == CURRENT_SOURCE_PROVIDER
    assert current_payload["observations"][0]["location_id"] == "station_05480"
    assert current_payload["observations"][0]["observed_at_utc"] == _iso(canonical_time)
    assert current_payload["observations"][0]["value"] == 12.0
    assert health_payload["verification_reference"]["id"] == "station_05480"
    assert dwd_health["last_observed_at_utc"] == _iso(canonical_time)
    assert dwd_health["freshness_state"] == "fresh"
    assert dwd_health["reason_code"] == "FRESH"
    assert _iso(newer_hourly_time) != dwd_health["last_observed_at_utc"]
    assert _iso(legacy_time) != dwd_health["last_observed_at_utc"]


def test_pre_cutover_hourly_status_cannot_satisfy_current_health(tmp_path) -> None:
    settings = Settings.from_env({"DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}"})
    database = Database(settings.database_url)
    client = TestClient(create_app(settings=settings, database=database))

    now = datetime.now(timezone.utc).replace(microsecond=0)
    database.set_provider_status(
        "dwd_observations",
        state="ok",
        now=now,
        model_name="DWD CDC Observations",
        init_time=now - timedelta(minutes=10),
    )

    current = client.get("/api/current")
    health = client.get("/api/health/providers")
    assert current.status_code == 200
    assert current.json()["observations"] == []

    dwd_health = next(item for item in health.json()["providers"] if item["id"] == "dwd_observations")
    assert dwd_health["last_observed_at_utc"] is None
    assert dwd_health["freshness_state"] == "unknown"
    assert dwd_health["reason_code"] == "SOURCE_TIME_MISSING"
