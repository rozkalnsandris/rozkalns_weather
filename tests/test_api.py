from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from rozkalns_weather.app import create_app
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database
from rozkalns_weather.locations import BENCHMARK_LOCATION
from rozkalns_weather.models import ForecastRun, ForecastValue, Observation


def _client(tmp_path, *, home: bool = False):
    env = {"DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}"}
    if home:
        env.update({"WEATHER_RUNTIME_MODE": "private-home", "HOME_LAT": "51.5", "HOME_LON": "7.6"})
    settings = Settings.from_env(env)
    database = Database(settings.database_url)
    return TestClient(create_app(settings=settings, database=database)), database


def test_health_root_and_core_provider_list(tmp_path) -> None:
    client, _ = _client(tmp_path)
    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 200
    providers = {item["id"]: item for item in client.get("/api/providers").json()["providers"]}
    assert set(providers) == {"weathernext3", "dwd_observations", "icon_d2", "ecmwf_ifs", "ecmwf_aifs"}
    assert providers["weathernext3"]["role"] == "optional_research"


def test_private_home_health_never_exposes_coordinates(tmp_path) -> None:
    client, _ = _client(tmp_path, home=True)
    response = client.get("/api/health/providers")
    assert response.status_code == 200
    assert response.json()["home"]["configured"] is True
    assert "51.5" not in response.text
    assert "7.6" not in response.text


def test_hourly_uses_immutable_station_snapshot(tmp_path) -> None:
    client, database = _client(tmp_path)
    init = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    run = ForecastRun(
        provider="icon_d2",
        model_provider="DWD",
        model_name="ICON-D2",
        model_version="fixture",
        init_time_utc=init,
        retrieved_at_utc=init + timedelta(minutes=10),
        source_surface="fixture",
        values=(
            ForecastValue(
                valid_time_utc=init + timedelta(hours=1),
                lead_hours=1,
                variable="temperature_2m",
                statistic="deterministic",
                value=12.5,
                unit="degC",
            ),
        ),
    )
    database.insert_forecast_run(run, location_id=BENCHMARK_LOCATION.id)
    payload = client.get("/api/hourly?location_id=station_05480&hours=6").json()
    assert payload["location"]["id"] == "station_05480"
    assert payload["series"][0]["provider"] == "icon_d2"
    assert payload["series"][0]["value"] == 12.5


def test_verification_summary_uses_station_05480_truth(tmp_path) -> None:
    client, database = _client(tmp_path)
    valid = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    database.insert_observations([
        Observation(
            source_provider="DWD",
            station_id="05480",
            location_id=BENCHMARK_LOCATION.id,
            observed_at_utc=valid,
            variable="temperature_2m",
            value=10.0,
            unit="degC",
        )
    ])
    for provider, value in (("icon_d2", 11.0), ("ecmwf_ifs", 10.5)):
        database.insert_forecast_run(
            ForecastRun(
                provider=provider,
                model_provider="DWD" if provider == "icon_d2" else "ECMWF",
                model_name=provider,
                model_version="fixture",
                init_time_utc=valid - timedelta(hours=6),
                retrieved_at_utc=valid - timedelta(hours=5),
                source_surface="fixture",
                values=(
                    ForecastValue(
                        valid_time_utc=valid,
                        lead_hours=6,
                        variable="temperature_2m",
                        statistic="deterministic",
                        value=value,
                        unit="degC",
                    ),
                ),
            ),
            location_id=BENCHMARK_LOCATION.id,
        )
    payload = client.get("/api/verification/summary?days=30").json()
    assert payload["comparison_location"]["id"] == "station_05480"
    assert {row["provider"] for row in payload["common_sample_slices"]} == {"icon_d2", "ecmwf_ifs"}

    compact = client.get("/api/verification/summary?days=30&compact=true").json()
    assert compact["comparison_location"]["id"] == "station_05480"
    assert {row["provider"] for row in compact["common_sample_slices"]} == {"icon_d2", "ecmwf_ifs"}
    assert "providers" not in compact
    assert all("matched_sample_ids" not in row for row in compact["common_sample_slices"])


def test_radar_map_proxy_keeps_private_home_coordinates_server_side(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, home=True)
    seen: list[tuple[float, float, str, str | None]] = []

    def fake_map(*, lat: float, lon: float, layer: str, at: str | None = None) -> bytes:
        seen.append((lat, lon, layer, at))
        return b"\x89PNG\r\n\x1a\nfixture"

    monkeypatch.setattr("rozkalns_weather.app_core.fetch_dwd_radar_map_png", fake_map)
    response = client.get("/api/radar/map?layer=radar&at=2026-09-28T12:30:00Z")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"].startswith("private")
    assert response.content.startswith(b"\x89PNG")
    assert seen == [(51.5, 7.6, "radar", "2026-09-28T12:30:00Z")]
    assert b"51.5" not in response.content
    assert b"7.6" not in response.content


def test_radar_map_requires_timestamp_for_radar_layer(tmp_path) -> None:
    client, _ = _client(tmp_path, home=True)
    assert client.get("/api/radar/map?layer=radar").status_code == 422


def test_unknown_location_is_rejected(tmp_path) -> None:
    client, _ = _client(tmp_path)
    assert client.get("/api/hourly?location_id=unknown").status_code == 422
