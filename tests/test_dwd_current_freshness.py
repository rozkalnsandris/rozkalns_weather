from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from rozkalns_weather.app import create_app
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database
from rozkalns_weather.models import Observation
from rozkalns_weather.providers.dwd_current_observations import CURRENT_MODEL_NAME, CURRENT_SOURCE_PROVIDER


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def test_current_and_health_share_05480_current_feed_time(tmp_path) -> None:
    settings = Settings.from_env({"DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}"})
    database = Database(settings.database_url)
    client = TestClient(create_app(settings=settings, database=database))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    canonical_time = now - timedelta(hours=1)
    database.insert_observations([
        Observation(
            source_provider=CURRENT_SOURCE_PROVIDER,
            station_id="05480",
            location_id="station_05480",
            observed_at_utc=canonical_time,
            variable="temperature_2m",
            value=12.0,
            unit="degC",
        )
    ])
    database.set_provider_status(
        "dwd_observations", state="ok", now=now,
        model_name=CURRENT_MODEL_NAME, init_time=canonical_time,
    )
    current = client.get("/api/current").json()
    health = client.get("/api/health/providers").json()
    dwd = next(item for item in health["providers"] if item["id"] == "dwd_observations")
    assert current["location"]["id"] == "station_05480"
    assert current["observations"][0]["observed_at_utc"] == _iso(canonical_time)
    assert dwd["last_observed_at_utc"] == _iso(canonical_time)
    assert dwd["freshness_state"] == "fresh"


def test_hourly_truth_status_does_not_fake_current_source_time(tmp_path) -> None:
    settings = Settings.from_env({"DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}"})
    database = Database(settings.database_url)
    client = TestClient(create_app(settings=settings, database=database))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    database.set_provider_status(
        "dwd_observations", state="ok", now=now,
        model_name="DWD CDC Observations", init_time=now - timedelta(minutes=10),
    )
    dwd = next(item for item in client.get("/api/health/providers").json()["providers"] if item["id"] == "dwd_observations")
    assert dwd["last_observed_at_utc"] is None
    assert dwd["reason_code"] == "SOURCE_TIME_MISSING"
