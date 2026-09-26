from fastapi.testclient import TestClient

from rozkalns_weather.app import create_app
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database


def _client(tmp_path, *, with_home: bool = False) -> TestClient:
    env = {"DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}"}
    if with_home:
        env.update({"HOME_LAT": "51.5", "HOME_LON": "7.6"})
    settings = Settings.from_env(env)
    return TestClient(create_app(settings=settings, database=Database(settings.database_url)))


def test_public_only_ui_defaults_to_canonical_station_05480(tmp_path) -> None:
    client = _client(tmp_path)
    html = client.get("/").text
    script = client.get("/static/app.js").text

    assert 'value="station_05480">DWD CDC 05480 · canonical public benchmark' in html
    assert 'value="station_10416">DWD 10416 · legacy MOSMIX reference' in html
    assert 'lastHealth.home.configured ? "home" : "station_05480"' in script
    assert 'lastHealth.home.configured ? "home" : "station_10416"' not in script
    assert 'station_05480: {' in script
    assert 'station_10416: {' in script
    assert 'DWD 10416 · legacy MOSMIX' in script
    assert 'Werl · official DWD observation source' in html
    assert 'DWD CDC 05480 reference observation' not in html
    assert 'DWD CDC 05480 station benchmark · deterministic' in html
    assert 'measured skill uses DWD CDC 05480 reference truth' in html
    assert 'DWD 10416 station benchmark · deterministic' not in html


def test_configured_home_remains_ui_default_contract(tmp_path) -> None:
    client = _client(tmp_path, with_home=True)
    health = client.get("/api/health/providers").json()
    script = client.get("/static/app.js").text

    assert health["home"]["configured"] is True
    assert health["home"]["coordinates_exposed"] is False
    assert 'lastHealth.home.configured ? "home" : "station_05480"' in script
    assert 'home: {' in script
    assert 'label: "Home"' in script
    assert "51.5" not in client.get("/api/health/providers").text
    assert "7.6" not in client.get("/api/health/providers").text


def test_forecast_location_api_whitelist_and_privacy_are_preserved(tmp_path) -> None:
    client = _client(tmp_path, with_home=True)

    for location_id in ("home", "station_05480", "station_10416"):
        hourly = client.get(f"/api/hourly?location_id={location_id}")
        daily = client.get(f"/api/daily?location_id={location_id}")
        assert hourly.status_code == 200
        assert daily.status_code == 200
        assert hourly.json()["location"]["id"] == location_id
        assert daily.json()["location"]["id"] == location_id
        assert hourly.json()["location"]["coordinates_exposed"] is False
        assert daily.json()["location"]["coordinates_exposed"] is False
        assert "51.5" not in hourly.text
        assert "7.6" not in hourly.text

    assert client.get("/api/hourly?location_id=unknown").status_code == 422
    assert client.get("/api/daily?location_id=unknown").status_code == 422


def test_overview_models_queries_remain_selected_location_driven(tmp_path) -> None:
    client = _client(tmp_path)
    script = client.get("/static/app.js").text

    assert 'location_id=${locationId}' in script
    assert '`hourly-temperature-48-${locationId}`' in script
    assert '`hourly-precipitation-48-${locationId}`' in script
    assert '`daily-10-${locationId}`' in script
    assert 'const locationMeta = FORECAST_LOCATION_META[locationId]' in script
