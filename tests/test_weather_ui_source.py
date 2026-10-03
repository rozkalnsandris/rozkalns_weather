from pathlib import Path

ROOT = Path(__file__).parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"


def test_core_weather_ui_assets_are_loaded() -> None:
    index = (STATIC / "index.html").read_text()
    assert index.index('/static/app.js') < index.index('/static/weather_ui.js')
    for asset in ("accepted_ui.css", "daily_trend.js", "app.js", "weather_ui.js", "runtime_badge.js"):
        assert f"/static/{asset}" in index


def test_simple_ui_has_only_current_locations_and_models() -> None:
    html = (STATIC / "index.html").read_text()
    app = (STATIC / "app.js").read_text()
    weather = (STATIC / "weather_ui.js").read_text()
    text = html + app + weather
    assert "station_05480" in text
    assert "station_10416" not in text
    assert "dwd_mosmix_l" not in text
    assert "WeatherNext 3" in text
    assert "ICON-D2" in text
    assert "ECMWF IFS" in text
    assert "AIFS" in text


def test_service_worker_caches_the_loaded_shell() -> None:
    index = (STATIC / "index.html").read_text()
    worker = (STATIC / "sw.js").read_text()
    assert 'navigator.serviceWorker.register("/sw.js", { scope: "/" })' in (STATIC / "app.js").read_text()
    assert "/static/accuracy_v3.js" not in worker
    assert "/static/accuracy_v3.js" not in index
    assert "self.skipWaiting()" in worker
    assert "self.clients.claim()" in worker


def test_simple_radar_and_status_do_not_reference_removed_lazy_modules() -> None:
    index = (STATIC / "index.html").read_text()
    app = (STATIC / "app.js").read_text()
    navigation = (STATIC / "navigation_v1.js").read_text()
    worker = (STATIC / "sw.js").read_text()
    combined = index + app + navigation + worker

    assert 'id="radarCanvas"' in index
    assert 'id="radarTimeline"' in index
    assert 'id="radarPlay"' in index
    assert 'id="radarOutput"' not in index
    assert "function renderRadarPayload(payload)" in app
    assert "function drawRadarFrame(index)" in app
    assert "radar_timeline.js" not in combined
    assert "status_v1.js" not in combined
    assert "forecast_loading.js" not in worker
    assert "request_lifecycle.js" not in worker
    assert "pwa_lifecycle.js" not in worker
    assert 'id="statusWeatherNext"' not in index
