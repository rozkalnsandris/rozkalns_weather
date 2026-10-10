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
    assert '/static/app.js?v=51' in index
    assert '"/static/app.js?v=51"' in worker
    assert "ASSETS.map((asset) => new URL(asset, self.location.origin).pathname)" in worker
    assert "ignoreSearch: true" not in worker


def test_weathernext_research_status_does_not_claim_recurring_freshness() -> None:
    app = (STATIC / "app.js").read_text()
    assert 'provider.id === "weathernext3" && provider.freshness_state === "not_tracked"' in app
    assert 'provider.state === "snapshot_available" ? "research"' in app
    assert 'provider.state === "not_ingested" ? "pending"' in app
    assert "Research snapshot ${formatTimestamp(updatedAt)}" in app
    assert "No research snapshot yet" in app
    assert 'researchState || normalizedProviderState(provider)' in app
    assert 'const tracked = (health.providers || []).filter((provider) => PUBLIC_PROVIDER_IDS.has(provider.id));' in app


def test_simple_radar_and_status_do_not_reference_removed_lazy_modules() -> None:
    index = (STATIC / "index.html").read_text()
    app = (STATIC / "app.js").read_text()
    navigation = (STATIC / "navigation_v1.js").read_text()
    worker = (STATIC / "sw.js").read_text()
    combined = index + app + navigation + worker

    assert 'id="radarMap"' in index
    assert 'id="radarImage"' not in index
    assert 'id="radarCanvas"' not in index
    assert '/static/vendor/leaflet/leaflet.css' in index
    assert '/static/vendor/leaflet/leaflet.js' in index
    assert "unpkg.com/leaflet" not in index
    leaflet_js = (STATIC / "vendor" / "leaflet" / "leaflet.js").read_text()
    leaflet_css = (STATIC / "vendor" / "leaflet" / "leaflet.css").read_text()
    assert "Leaflet 1.9.4" in leaflet_js
    assert ".leaflet-container" in leaflet_css
    assert 'id="radarTimeline"' not in index
    assert 'id="radarPlay"' not in index
    assert 'id="radarOutput"' not in index
    assert "function renderRadarPayload(payload)" in app
    assert "function refreshRadarMapImage()" in app
    assert 'L.map("radarMap"' in app
    assert "L.imageOverlay(url, bounds" in app
    assert "https://tile.openstreetmap.org" not in app
    assert "L.tileLayer.wms" not in app
    assert "https://maps.dwd.de" not in app
    assert "RADAR_PUBLIC_CENTER = [51.532, 7.611]" in app
    assert "/api/radar/map?" in app
    assert "/api/radar/basemap?" in app
    assert "radarBaseLayer = L.imageOverlay(basemapUrl, bounds" in app
    assert "radarBaseLayer.setUrl(basemapUrl)" in app
    assert "const observedFrames = frames.filter((frame) => frame.kind === \"radar_observed\")" in app
    assert "radarFrame = observedFrames[observedFrames.length - 1]" in app
    assert "basemap.de" in app
    assert "© GeoBasis-DE / BKG" in app
    assert "minZoom: 11" in app
    assert "sgx.geodatenzentrum.de" not in app
    assert "https://tile.openstreetmap.org" not in app
    api = (ROOT / "src" / "rozkalns_weather" / "app_core.py").read_text()
    assert '@app.get("/api/radar/basemap")' in api
    assert 'fetch_bkg_basemap_png(west=west, south=south, east=east, north=north)' in api
    assert 'radarMap.on("moveend"' in app
    assert "radarPlaybackTimer" not in app
    assert "preloadRadarFrameMaps" not in app
    assert "radarCellColor" not in app
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
    assert "No WeatherNext forecast for Home. Station 05480 research snapshots are separate." in model_alignment
    assert "No matching WeatherNext forecast for this location and time." in model_alignment
    assert 'querySelector("#forecastLocation")' in model_alignment
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
    assert "rozkalns-weather-v51" in worker


def _wcag_contrast(foreground: str, background: str) -> float:
    def luminance(hex_color: str) -> float:
        values = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
        return sum(a * b for a, b in zip(linear, (0.2126, 0.7152, 0.0722)))

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_galaxy_warning_text_and_fresh_chip_contrast_in_both_themes() -> None:
    css = (STATIC / "accepted_ui.css").read_text()
    html = (STATIC / "index.html").read_text()
    assert 'id="warningsOutput" class="warning-readable"' in html
    assert "html[data-ui-theme] .warning-readable { color:var(--ink); }" in css
    assert "html[data-ui-theme] .warning-readable summary { color:var(--accent); }" in css
    assert "html[data-ui-theme] .radar-legend { color:var(--muted); }" in css
    assert "html[data-ui-theme] .state-chip.state-fresh { color:#145d38; background:#e5f7eb; border-color:#2c875b; }" in css
    assert "html[data-ui-theme=dark] .state-chip.state-fresh { color:#e0f9eb; background:#174533; border-color:#77bf93; }" in css
    assert "html[data-ui-theme] { color-scheme:light; --bg:#f0f5fa; --card:#fff; --ink:#203b54;" in css
    assert "html[data-ui-theme=dark] { color-scheme:dark; --bg:#101b29; --card:#18293b; --ink:#e7f0f8;" in css
    assert _wcag_contrast("#203b54", "#ffffff") >= 4.5
    assert _wcag_contrast("#e7f0f8", "#18293b") >= 4.5
    assert _wcag_contrast("#145d38", "#e5f7eb") >= 4.5
    assert _wcag_contrast("#e0f9eb", "#174533") >= 4.5
    assert _wcag_contrast("#286f9e", "#ffffff") >= 4.5
    assert _wcag_contrast("#8bc2ef", "#18293b") >= 4.5
