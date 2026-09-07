from fastapi.testclient import TestClient

from rozkalns_weather.app import create_app
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database


def _client(tmp_path, *, with_home: bool = True) -> TestClient:
    env = {"DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}"}
    if with_home:
        env.update({"HOME_LAT": "51.5", "HOME_LON": "7.6"})
    settings = Settings.from_env(env)
    database = Database(settings.database_url)
    return TestClient(create_app(settings=settings, database=database))


def test_health_is_ready(tmp_path) -> None:
    response = _client(tmp_path).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ready"}


def test_weather_next_is_first_class_provider(tmp_path) -> None:
    response = _client(tmp_path).get("/api/providers")
    providers = response.json()["providers"]
    weather_next = next(item for item in providers if item["id"] == "weathernext3")
    assert weather_next["role"] == "primary_research"
    assert weather_next["model_name"] == "WeatherNext 3"


def test_provider_health_does_not_expose_home_coordinates(tmp_path) -> None:
    response = _client(tmp_path).get("/api/health/providers")
    payload = response.json()
    assert payload["location"]["configured"] is True
    assert payload["location"]["coordinates_exposed"] is False
    assert "51.5" not in response.text
    assert "7.6" not in response.text
