from fastapi.testclient import TestClient

import rozkalns_weather.app_core as app_core_module
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database
from rozkalns_weather.locations import DWD_CDC_05480


def _client(tmp_path, *, home: bool = False, raise_server_exceptions: bool = True):
    env = {"DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}"}
    if home:
        env.update({
            "WEATHER_RUNTIME_MODE": "private-home",
            "HOME_LAT": "51.5",
            "HOME_LON": "7.6",
            "HOME_LABEL": "Private home",
        })
    settings = Settings.from_env(env)
    database = Database(settings.database_url)
    return TestClient(
        app_core_module.create_app(settings=settings, database=database),
        raise_server_exceptions=raise_server_exceptions,
    )


def test_public_safety_uses_05480_reference_without_exposing_coordinates(tmp_path, monkeypatch):
    calls = {}
    monkeypatch.setattr(app_core_module, "fetch_dwd_alerts", lambda *, lat, lon: calls.setdefault("warnings", (lat, lon)) and {"authority":"DWD","official":True,"alerts":[]})
    monkeypatch.setattr(app_core_module, "fetch_radar_point", lambda *, lat, lon, center_location_id: calls.setdefault("radar", (lat, lon, center_location_id)) and {"not_model_forecast":True,"map_contract":{"center_location_id":center_location_id,"coordinates_exposed":False}})
    client = _client(tmp_path)
    warnings = client.get("/api/warnings")
    radar = client.get("/api/radar")
    assert calls["warnings"] == (DWD_CDC_05480.lat, DWD_CDC_05480.lon)
    assert calls["radar"] == (DWD_CDC_05480.lat, DWD_CDC_05480.lon, "station_05480")
    assert warnings.json()["authority"] == "DWD"
    assert warnings.json()["reference_location"]["coordinates_exposed"] is False
    assert radar.json()["reference_location"]["coordinates_exposed"] is False


def test_private_home_reference_is_runtime_only(tmp_path, monkeypatch):
    calls = {}
    monkeypatch.setattr(app_core_module, "fetch_dwd_alerts", lambda *, lat, lon: calls.setdefault("warnings", (lat, lon)) and {"authority":"DWD","official":True,"alerts":[]})
    monkeypatch.setattr(app_core_module, "fetch_radar_point", lambda *, lat, lon, center_location_id: calls.setdefault("radar", (lat, lon, center_location_id)) and {"not_model_forecast":True,"map_contract":{"center_location_id":center_location_id,"coordinates_exposed":False}})
    client = _client(tmp_path, home=True)
    warnings = client.get("/api/warnings")
    radar = client.get("/api/radar")
    assert calls["warnings"] == (51.5, 7.6)
    assert calls["radar"] == (51.5, 7.6, "home")
    assert "51.5" not in warnings.text
    assert "7.6" not in radar.text


def test_upstream_warning_failure_is_not_fabricated(tmp_path, monkeypatch):
    def fail(*, lat, lon):
        raise RuntimeError("upstream unavailable")
    monkeypatch.setattr(app_core_module, "fetch_dwd_alerts", fail)
    response = _client(tmp_path, raise_server_exceptions=False).get("/api/warnings")
    assert response.status_code == 500
