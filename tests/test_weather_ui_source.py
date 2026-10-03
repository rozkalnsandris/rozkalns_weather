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

    assert 'id="radarBaseMap"' in index
    assert 'id="radarImage"' in index
    assert 'id="radarBoundaries"' in index
    assert 'id="radarCanvas"' in index
    assert 'id="radarTimeline"' in index
    assert 'id="radarPlay"' in index
    assert 'id="radarOutput"' not in index
    assert "function renderRadarPayload(payload)" in app
    assert "function drawRadarFrame(index)" in app
    assert '"/api/radar/map?"' not in app
    assert "/api/radar/map?" in app
    assert 'new URLSearchParams({ layer })' in app
    assert "preloadRadarFrameMaps" in app
    assert "radar_timeline.js" not in combined
    assert "status_v1.js" not in combined
    assert "forecast_loading.js" not in worker
    assert "request_lifecycle.js" not in worker
    assert "pwa_lifecycle.js" not in worker
    assert 'id="statusWeatherNext"' not in index


def test_simple_ui_hides_internal_research_controls() -> None:
    html = (STATIC / "index.html").read_text()
    app = (STATIC / "app.js").read_text()
    model_alignment = (STATIC / "model_snapshot_alignment.js").read_text()
    worker = (STATIC / "sw.js").read_text()

    assert "Value provenance" not in html
    assert "Provider classes" not in html
    assert "verification lineage" not in html
    assert "descriptive provider disagreement" not in app
    assert "descriptive provider disagreement" not in model_alignment
    assert "provider state" not in model_alignment
    assert "no genuine WeatherNext forecast value available" not in model_alignment
    assert "WeatherNext data has not been collected yet." in model_alignment
    assert "Model difference" in model_alignment
    assert "/static/provenance_v1.js" not in html
    assert "/static/provenance_v1.js" not in worker
    assert not (STATIC / "provenance_v1.js").exists()
    assert "WeatherNext 3" in html
    assert "DWD official warnings" in html
    assert "Forecast sources" in html


def test_mobile_interaction_stays_compact_and_direct() -> None:
    html = (STATIC / "index.html").read_text()
    app = (STATIC / "app.js").read_text()
    consumer = (STATIC / "consumer_ui.js").read_text()
    accepted = (STATIC / "accepted_ui.css").read_text()
    worker = (STATIC / "sw.js").read_text()

    assert "min-height:300px" not in html
    assert 'behavior: "smooth"' not in app
    assert 'behavior: "auto"' in app
    assert "forecast for ${berlinLocalTime(anchor.valid_time_utc)}" in consumer
    assert " · retrieved ${anchor.retrieved_at_utc" not in consumer
    assert "grid-template-columns:repeat(3,minmax(0,1fr))" in accepted
    assert 'input[type="range"]' in accepted
    assert "min-height:44px" in accepted
    assert "compact=true" in app
    assert "Loading accuracy…" in app
    assert "requestIdleCallback" in app
    assert "accuracyPayloads" in app
    assert "registration.update()" in app
    assert 'fetch(event.request, { cache: "no-cache" })' in worker
    assert "provider.last_observed_at_utc" in app
    assert ".chart{overflow:hidden}" in (STATIC / "app.css").read_text()
    assert ".chart svg{display:block;min-width:0;max-width:100%;height:auto}" in (STATIC / "app.css").read_text()
    time_semantics = (STATIC / "time_semantics.js").read_text()
    assert " · ${identity.utc}" not in time_semantics
    assert "rozkalns-weather-v44" in worker
