from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from rozkalns_weather.app import create_app
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database
from rozkalns_weather.locations import DWD_10416
from rozkalns_weather.models import ForecastRun, ForecastValue, Observation


def _client(tmp_path, *, with_home: bool = True) -> tuple[TestClient, Database]:
    env = {"DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}"}
    if with_home:
        env.update({"HOME_LAT": "51.5", "HOME_LON": "7.6"})
    settings = Settings.from_env(env)
    database = Database(settings.database_url)
    return TestClient(create_app(settings=settings, database=database)), database


def test_health_and_pwa_root(tmp_path) -> None:
    client, _ = _client(tmp_path)
    assert client.get("/health").status_code == 200
    root = client.get("/")
    assert root.status_code == 200
    assert "WeatherNext 3" in root.text


def test_weather_next_is_first_class_provider(tmp_path) -> None:
    client, _ = _client(tmp_path)
    providers = client.get("/api/providers").json()["providers"]
    weather_next = next(item for item in providers if item["id"] == "weathernext3")
    assert weather_next["role"] == "primary_research"
    assert weather_next["model_name"] == "WeatherNext 3"


def test_provider_health_does_not_expose_home_coordinates(tmp_path) -> None:
    client, _ = _client(tmp_path)
    response = client.get("/api/health/providers")
    payload = response.json()
    assert payload["location"]["configured"] is True
    assert payload["location"]["coordinates_exposed"] is False
    assert "51.5" not in response.text
    assert "7.6" not in response.text
    tracked = {item["id"]: item for item in payload["providers"]}
    assert payload["health_contract"] == "provider-freshness-v1"
    for provider_id in ("dwd_observations", "dwd_mosmix_l", "icon_d2", "ecmwf_ifs", "ecmwf_aifs"):
        assert tracked[provider_id]["tracked"] is True
        assert tracked[provider_id]["freshness_state"] == "not_ingested"
        assert tracked[provider_id]["failure_domain"] == "local_ingest_not_started"
    assert tracked["weathernext3"]["tracked"] is False


def test_provider_health_pwa_exposes_freshness_and_failure_domain(tmp_path) -> None:
    client, _ = _client(tmp_path)
    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert "freshness_state" in script.text
    assert "failure_domain" in script.text
    assert "last_retrieved_at_utc" in script.text


def test_hourly_returns_latest_provider_snapshot(tmp_path) -> None:
    client, database = _client(tmp_path)
    database.insert_forecast_run(ForecastRun(
        provider="weathernext3", model_provider="Google DeepMind", model_name="WeatherNext 3", model_version="3.0.0",
        init_time_utc=datetime(2026, 9, 7, 0, tzinfo=timezone.utc), retrieved_at_utc=datetime(2026, 9, 7, 8, tzinfo=timezone.utc),
        source_surface="test", values=(ForecastValue(valid_time_utc=datetime(2026,9,7,12,tzinfo=timezone.utc), lead_hours=12, variable="temperature_2m", statistic="mean", value=20, unit="degC"),)
    ))
    response = client.get("/api/hourly?hours=48")
    assert response.status_code == 200
    payload = response.json()
    assert payload["location"]["coordinates_exposed"] is False
    assert payload["series"][0]["provider"] == "weathernext3"


def test_verification_api_uses_common_samples_and_exposes_missingness(tmp_path) -> None:
    client, database = _client(tmp_path)
    first = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    second = first + timedelta(hours=1)
    database.insert_observations(
        [
            Observation(
                source_provider="DWD",
                station_id="10416",
                location_id=DWD_10416.id,
                observed_at_utc=valid,
                variable="temperature_2m",
                value=value,
                unit="degC",
            )
            for valid, value in ((first, 10.0), (second, 11.0))
        ]
    )

    database.insert_forecast_run(
        ForecastRun(
            provider="icon_d2",
            model_provider="DWD",
            model_name="ICON-D2",
            model_version="icon-v1",
            init_time_utc=first - timedelta(hours=6),
            retrieved_at_utc=first - timedelta(hours=5),
            source_surface="fixture",
            values=(
                ForecastValue(
                    valid_time_utc=first,
                    lead_hours=6,
                    variable="temperature_2m",
                    statistic="deterministic",
                    value=11.0,
                    unit="degC",
                ),
                ForecastValue(
                    valid_time_utc=second,
                    lead_hours=7,
                    variable="temperature_2m",
                    statistic="deterministic",
                    value=12.0,
                    unit="degC",
                ),
            ),
        ),
        location_id=DWD_10416.id,
    )
    database.insert_forecast_run(
        ForecastRun(
            provider="ecmwf_ifs",
            model_provider="ECMWF",
            model_name="IFS HRES",
            model_version="ifs-v1",
            init_time_utc=first - timedelta(hours=6),
            retrieved_at_utc=first - timedelta(hours=5),
            source_surface="fixture",
            values=(
                ForecastValue(
                    valid_time_utc=first,
                    lead_hours=6,
                    variable="temperature_2m",
                    statistic="deterministic",
                    value=10.5,
                    unit="degC",
                ),
            ),
        ),
        location_id=DWD_10416.id,
    )

    response = client.get("/api/verification/summary?days=30")
    assert response.status_code == 200
    payload = response.json()
    assert payload["sample_sufficiency_contract"] == "common-sample-sufficiency-v1"
    assert len(payload["common_sample_slices"]) == 2
    rows = {row["provider"]: row for row in payload["common_sample_slices"]}
    assert rows["icon_d2"]["n"] == 1
    assert rows["icon_d2"]["missingness"]["expected_n"] == 2
    assert rows["icon_d2"]["missingness"]["missing_n"] == 0
    assert rows["icon_d2"]["missingness"]["excluded_non_common_n"] == 1
    assert rows["ecmwf_ifs"]["missingness"]["missing_n"] == 1
    assert rows["ecmwf_ifs"]["sample_sufficiency_state"] == "insufficient_sample"
    assert payload["providers"]["icon_d2"]["descriptive_only"] is True

    script = client.get("/static/app.js").text
    assert "common_sample_slices" in script
    assert "sample_sufficiency_state" in script
    assert "missingness" in script
