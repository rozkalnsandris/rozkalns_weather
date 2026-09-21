from fastapi.testclient import TestClient

import rozkalns_weather.app as app_module
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database
from rozkalns_weather.locations import DWD_CDC_05480


def _client(tmp_path, *, with_home: bool = False, runtime_mode: str = "public-only", raise_server_exceptions: bool = True):
    env = {
        "DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}",
        "WEATHER_RUNTIME_MODE": runtime_mode,
    }
    if with_home:
        env.update({"HOME_LAT": "51.5", "HOME_LON": "7.6", "HOME_LABEL": "Private home"})
    settings = Settings.from_env(env)
    database = Database(settings.database_url)
    return TestClient(
        app_module.create_app(settings=settings, database=database),
        raise_server_exceptions=raise_server_exceptions,
    )


def test_public_only_safety_uses_reviewed_public_reference_without_exposing_coordinates(tmp_path, monkeypatch):
    calls = {}

    def fake_alerts(*, lat, lon):
        calls["warnings"] = (lat, lon)
        return {"authority": "DWD", "official": True, "kind": "official_warning", "alerts": [], "coordinates_exposed": False}

    def fake_radar(*, lat, lon, center_location_id):
        calls["radar"] = (lat, lon, center_location_id)
        return {
            "source": "DWD radar fixture",
            "not_model_forecast": True,
            "map_contract": {"center_location_id": center_location_id, "coordinates_exposed": False},
            "frames": [],
        }

    monkeypatch.setattr(app_module, "fetch_dwd_alerts", fake_alerts)
    monkeypatch.setattr(app_module, "fetch_radar_point", fake_radar)
    client = _client(tmp_path)

    warnings = client.get("/api/warnings")
    radar = client.get("/api/radar")
    assert warnings.status_code == 200
    assert radar.status_code == 200
    assert calls["warnings"] == (DWD_CDC_05480.lat, DWD_CDC_05480.lon)
    assert calls["radar"] == (DWD_CDC_05480.lat, DWD_CDC_05480.lon, "station_05480")

    for response in (warnings, radar):
        reference = response.json()["reference_location"]
        assert reference == {
            "id": "station_05480",
            "label": "DWD CDC Werl 05480",
            "station_id": "05480",
            "context": "public_reference",
            "coordinates_exposed": False,
        }
        assert "lat" not in reference
        assert "lon" not in reference

    assert warnings.json()["authority"] == "DWD"
    assert warnings.json()["official"] is True
    assert radar.json()["not_model_forecast"] is True
    assert radar.json()["map_contract"]["center_location_id"] == "station_05480"


def test_configured_home_safety_keeps_private_home_reference_without_exposing_coordinates(tmp_path, monkeypatch):
    calls = {}

    def fake_alerts(*, lat, lon):
        calls["warnings"] = (lat, lon)
        return {"authority": "DWD", "official": True, "alerts": [], "coordinates_exposed": False}

    def fake_radar(*, lat, lon, center_location_id):
        calls["radar"] = (lat, lon, center_location_id)
        return {"not_model_forecast": True, "map_contract": {"center_location_id": center_location_id, "coordinates_exposed": False}}

    monkeypatch.setattr(app_module, "fetch_dwd_alerts", fake_alerts)
    monkeypatch.setattr(app_module, "fetch_radar_point", fake_radar)
    client = _client(tmp_path, with_home=True)

    warnings = client.get("/api/warnings")
    radar = client.get("/api/radar")
    assert calls["warnings"] == (51.5, 7.6)
    assert calls["radar"] == (51.5, 7.6, "home")
    assert warnings.json()["reference_location"] == {
        "id": "home",
        "label": "Private home",
        "context": "configured_private_home",
        "coordinates_exposed": False,
    }
    assert radar.json()["reference_location"]["id"] == "home"
    assert "51.5" not in warnings.text
    assert "7.6" not in warnings.text
    assert "51.5" not in radar.text
    assert "7.6" not in radar.text


def test_private_research_without_home_remains_fail_closed(tmp_path):
    client = _client(tmp_path, runtime_mode="private-research")
    assert client.get("/api/warnings").status_code == 503
    assert client.get("/api/radar").status_code == 503


def test_upstream_failure_is_not_replaced_with_fabricated_safety_data(tmp_path, monkeypatch):
    def fail_alerts(*, lat, lon):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(app_module, "fetch_dwd_alerts", fail_alerts)
    client = _client(tmp_path, raise_server_exceptions=False)
    response = client.get("/api/warnings")
    assert response.status_code == 500
    assert "alerts_present" not in response.text
    assert "no_active_alerts" not in response.text


def test_safety_ui_explains_public_reference_and_dwd_authority(tmp_path):
    client = _client(tmp_path)
    html = client.get("/").text
    assert "DWD official warnings" in html
    assert "DWD warning slānis ir autoritatīvs" in html
    assert "public-only režīmā warnings izmanto publisko DWD CDC Werl 05480 reference punktu" in html
    assert "Public-only režīmā bez privāta home punkta centrs ir publiskais DWD CDC Werl 05480 reference punkts" in html
