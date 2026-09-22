from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from rozkalns_weather.app import create_app
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database
from rozkalns_weather.locations import DWD_CDC_05480
from rozkalns_weather.models import Observation


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def test_current_and_health_share_canonical_05480_source_time(tmp_path) -> None:
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
    legacy_time = now - timedelta(minutes=5)
    database.insert_observations(
        [
            Observation(
                source_provider="DWD",
                station_id="05480",
                location_id="station_05480",
                observed_at_utc=canonical_time,
                variable="temperature_2m",
                value=12.0,
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
        model_name="DWD CDC Observations",
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
    assert current_payload["observations"][0]["location_id"] == "station_05480"
    assert current_payload["observations"][0]["observed_at_utc"] == _iso(canonical_time)
    assert health_payload["verification_reference"]["id"] == "station_05480"
    assert dwd_health["last_observed_at_utc"] == _iso(canonical_time)
    assert dwd_health["freshness_state"] == "fresh"
    assert dwd_health["reason_code"] == "FRESH"
    assert _iso(legacy_time) != dwd_health["last_observed_at_utc"]
