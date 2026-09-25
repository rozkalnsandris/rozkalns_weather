from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from rozkalns_weather.app import create_app
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database
from rozkalns_weather.locations import DWD_CDC_05480
from rozkalns_weather.models import ForecastRun, ForecastValue, Observation


def _client(tmp_path, *, with_home: bool = True) -> tuple[TestClient, Database]:
    env = {"DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}"}
    if with_home:
        env.update({"HOME_LAT": "51.5", "HOME_LON": "7.6"})
    settings = Settings.from_env(env)
    database = Database(settings.database_url)
    return TestClient(create_app(settings=settings, database=database)), database


def _ensure_benchmark(database: Database) -> None:
    database.ensure_location(
        location_id=DWD_CDC_05480.id,
        label=DWD_CDC_05480.label,
        lat=DWD_CDC_05480.lat,
        lon=DWD_CDC_05480.lon,
        elevation_m=DWD_CDC_05480.elevation_m,
        timezone=DWD_CDC_05480.timezone,
    )


def _run(valid: datetime) -> ForecastRun:
    return ForecastRun(
        provider="icon_d2",
        model_provider="DWD",
        model_name="ICON-D2",
        model_version="icon-v1",
        init_time_utc=datetime(2026, 9, 25, 6, tzinfo=timezone.utc),
        retrieved_at_utc=datetime(2026, 9, 25, 7, tzinfo=timezone.utc),
        source_surface="fixture",
        transport_provider="DWD",
        values=(
            ForecastValue(
                valid_time_utc=valid,
                lead_hours=6,
                variable="temperature_2m",
                statistic="deterministic",
                value=18.0,
                unit="degC",
                native_value=291.15,
                native_unit="K",
            ),
            ForecastValue(
                valid_time_utc=valid,
                lead_hours=6,
                variable="precipitation_1h",
                statistic="deterministic",
                value=0.4,
                unit="mm",
                accumulation_window_minutes=60,
            ),
        ),
    )


def test_hourly_api_adds_trace_without_expanding_legacy_top_level_surface(tmp_path) -> None:
    client, database = _client(tmp_path)
    valid = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
    database.insert_forecast_run(_run(valid))

    response = client.get("/api/hourly?hours=48&variable=temperature_2m&location_id=home")
    assert response.status_code == 200
    row = response.json()["series"][0]
    assert row["provider"] == "icon_d2"
    assert row["model_version"] == "icon-v1"
    assert row["statistic"] == "deterministic"
    assert "raw_payload_hash" not in row
    assert "source_surface" not in row
    assert "native_value" not in row

    trace = row["provenance_trace"]
    assert trace["state"] == "PASS"
    assert trace["location"] == {"id": "home", "scope": "private_home", "coordinates_exposed": False}
    assert trace["source"]["provider"] == "icon_d2"
    assert trace["source"]["source_surface"] == "fixture"
    assert trace["normalized_value"]["variable"] == "temperature_2m"
    assert trace["normalized_value"]["statistic"] == "deterministic"
    assert len(trace["snapshot"]["id"]) == 64
    assert len(trace["trace_identity_sha256"]) == 64
    assert trace["privacy"] == {
        "coordinates_exposed": False,
        "database_path_exposed": False,
        "credentials_exposed": False,
        "raw_logs_exposed": False,
    }

    lowered = response.text.lower()
    assert "51.5" not in lowered
    assert "7.6" not in lowered
    assert "home_lat" not in lowered
    assert "home_lon" not in lowered
    assert "sqlite:///" not in lowered
    assert "/private/" not in lowered


def test_station_verification_trace_binds_dwd_truth_and_metric(tmp_path) -> None:
    client, database = _client(tmp_path, with_home=False)
    _ensure_benchmark(database)
    valid = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
    database.insert_forecast_run(_run(valid), location_id=DWD_CDC_05480.id)
    database.insert_observations([
        Observation(
            source_provider="DWD",
            station_id="05480",
            location_id=DWD_CDC_05480.id,
            observed_at_utc=valid,
            variable="temperature_2m",
            value=18.2,
            unit="degC",
        )
    ])

    response = client.get(
        "/api/provenance/verification",
        params={
            "provider": "icon_d2",
            "valid_time_utc": "2026-09-25T12:00:00Z",
            "variable": "temperature_2m",
            "statistic": "deterministic",
            "metric_name": "absolute_error",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "PASS"
    assert payload["forecast"]["location"]["id"] == "station_05480"
    assert payload["truth"]["source"] == {"provider": "DWD", "station_id": "05480"}
    assert payload["truth"]["time"]["observed_at_utc"] == "2026-09-25T12:00:00Z"
    assert payload["metric_identity"] == {
        "name": "absolute_error",
        "version": 1,
        "comparison_mode": "station_run_skill",
        "location_id": "station_05480",
    }
    assert payload["privacy"]["coordinates_exposed"] is False


def test_verification_trace_returns_stable_blocked_reason_when_value_is_missing(tmp_path) -> None:
    client, database = _client(tmp_path, with_home=False)
    _ensure_benchmark(database)

    response = client.get(
        "/api/provenance/verification",
        params={
            "provider": "icon_d2",
            "valid_time_utc": "2026-09-25T12:00:00Z",
        },
    )
    assert response.status_code == 404
    assert response.json()["state"] == "BLOCKED"
    assert response.json()["reason_codes"] == ["FORECAST_VALUE_NOT_FOUND"]


def test_pwa_loads_provenance_drilldown_and_keeps_provider_values_separate(tmp_path) -> None:
    client, _ = _client(tmp_path)
    root = client.get("/")
    script = client.get("/static/provenance_v1.js")

    assert root.status_code == 200
    assert '/static/provenance_v1.js' in root.text
    assert script.status_code == 200
    for field in (
        "snapshot.id",
        "source.model_name",
        "source.model_version",
        "time.init_time_utc",
        "time.valid_time_utc",
        "time.lead_hours",
        "time.retrieved_at_utc",
        "normalized.statistic",
        "truth_trace_identity_sha256",
        "metric_identity",
    ):
        assert field in script.text
    assert "/api/provenance/verification" in script.text
    assert "station_05480" in script.text
    assert "Combined" not in script.text
