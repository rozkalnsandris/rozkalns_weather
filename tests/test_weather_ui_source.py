from pathlib import Path
import shutil
import subprocess

import pytest

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
    assert '/static/app.js?v=58' in index
    assert '"/static/app.js?v=58"' in worker
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
    assert "const RADAR_OVERLAY_OPACITY = 0.35;" in app
    assert "radarImageLayer = L.imageOverlay(url, bounds, { opacity: RADAR_OVERLAY_OPACITY })" in app
    assert "radarBaseLayer = L.imageOverlay(basemapUrl, bounds, { opacity: 1" in app
    assert "rain colours are translucent so streets remain visible" in index.lower()
    assert "radarImageLayer = L.imageOverlay(url, bounds, { opacity: 1 })" not in app
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
    assert "rozkalns-weather-v58" in worker


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


def test_home_overview_does_not_mislabel_station_or_fabricate_missing_data() -> None:
    app = (STATIC / "app.js").read_text()
    weather = (STATIC / "weather_ui.js").read_text()
    index = (STATIC / "index.html").read_text()

    assert 'label: "Dortmund-Wickede · reference"' in app
    assert 'station_05480: "Dortmund-Wickede · reference"' in weather
    assert "observed weather comes from DWD CDC Werl 05480" in app
    assert '<h1 id="heroLocation">Dortmund-Wickede · reference</h1>' in index
    assert "No upcoming hourly forecast is available." in app
    assert 'setSurfaceState("overviewTempState", "stale", "No upcoming hourly forecast is available.")' in app
    assert "return (upcoming.length ? upcoming : rows.slice(-count)).slice(0, count)" not in app + weather
    assert app.count("return upcoming.slice(0, count);") == 1
    assert weather.count("return upcoming.slice(0, count);") == 1
    assert "const hourly = rows.some((row) => row.valid_time_utc)" in app
    assert "const available = new Set(futureRows(tempRows || []" in weather
    assert 'temp?.value != null && temp.value !== ""' in app
    assert "const precipitationFor = (anchor) => {" in app
    assert "anchor.init_time_utc !== row.init_time_utc" in app
    assert 'row.value == null || row.value === ""' in app
    assert 'const rain = precipitationFor(row);' in app
    assert 'const rains = tempSeries.map(precipitationFor);' in app
    assert 'if (value == null) return "";' in app
    assert 'Number(row.value) ?? 0' not in app



def test_daily_provider_choice_supports_7_and_14_days_without_mixing_models() -> None:
    if not shutil.which("node"):
        pytest.skip("Node.js is not installed")
    script = r"""
const assert = require("node:assert/strict");
const daily = require(process.argv[1]);
const preferred = ["weathernext3", "icon_d2", "ecmwf_ifs", "ecmwf_aifs"];
const days = (provider, count) => Array.from({length: count}, (_, i) => ({
  provider,
  date: new Date(Date.UTC(2026, 9, 10 + i)).toISOString().slice(0, 10),
  temperature_min_c: 5,
  temperature_max_c: 14
}));
const rows = [...days("icon_d2", 3), ...days("ecmwf_ifs", 7), ...days("ecmwf_aifs", 15)];
assert.equal(daily.chooseProvider(rows, "2026-10-10", preferred), "ecmwf_aifs");
assert.equal(daily.select(rows, "ecmwf_aifs").length, 14);
assert.equal(daily.chooseProvider([...days("icon_d2", 3), ...days("ecmwf_ifs", 7)], "2026-10-10", preferred), "ecmwf_ifs");
assert.equal(daily.chooseProvider(days("icon_d2", 3), "2026-10-10", preferred), "icon_d2");
assert.equal(daily.chooseProvider([], "2026-10-10", preferred), null);
assert.equal(daily.chooseProvider([{provider:"ecmwf_aifs", date:"2026-10-11", temperature_min_c:null, temperature_max_c:null}], "2026-10-10", preferred), null);
assert.equal(daily.chooseProvider([...days("icon_d2", 3), ...days("ecmwf_ifs", 3)], "2026-10-10", preferred), "icon_d2");
assert.equal(daily.chooseProvider([...days("icon_d2", 3), ...days("ecmwf_aifs", 15)], "2026-10-16", preferred), "ecmwf_aifs");
"""
    result = subprocess.run(
        ["node", "-e", script, str(STATIC / "daily_trend.js")],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_next_days_chooses_real_long_range_provider_and_tracks_total_available_days() -> None:
    app = (STATIC / "app.js").read_text()
    daily = (STATIC / "daily_trend.js").read_text()
    weather = (STATIC / "weather_ui.js").read_text()
    assert "window.RozkalnsDailyTrend.chooseProvider(rows, localDateKey(), PROVIDER_PREFERENCE)" in app
    assert 'const api = { number, availableProviders, chooseProvider, select, geometry, amount, render };' in daily
    assert '${available.length} available day' in daily
    assert 'available.length <= 7 ? "disabled" : ""' in daily
    assert 'document.querySelector("#dailyGrid")?.dataset.provider' in weather


def test_next_days_versioned_dependencies_and_visible_render_failure() -> None:
    index = (STATIC / "index.html").read_text()
    worker = (STATIC / "sw.js").read_text()
    app = (STATIC / "app.js").read_text()
    assert '<script src="/static/daily_trend.js?v=58" defer></script>' in index
    assert '<script src="/static/app.js?v=58" defer></script>' in index
    assert index.index('/static/daily_trend.js?v=58') < index.index('/static/app.js?v=58')
    assert '"/static/daily_trend.js?v=58"' in worker
    assert '"/static/app.js?v=58"' in worker
    assert "rozkalns-weather-v58" in worker
    assert 'if (daily.status === "fulfilled") {' in app
    assert 'renderDaily(daily.value, healthMap);' in app
    assert 'catch (_error) {' in app
    assert 'qs("#dailyGrid").textContent = "Daily forecast could not be displayed. Refresh to retry.";' in app
    assert 'setSurfaceState("dailyState", "error", "Daily forecast could not be displayed. Refresh to retry.", { alert: true });' in app


def test_daily_trend_fixture_can_toggle_between_seven_and_fourteen_days() -> None:
    if not shutil.which("node"):
        pytest.skip("Node.js is not installed")
    script = r"""
const assert = require("node:assert/strict");
const daily = require(process.argv[1]);
const rows = Array.from({length:15}, (_,index)=>({
  provider:"ecmwf_aifs",
  date:new Date(Date.UTC(2026,9,10+index)).toISOString().slice(0,10),
  temperature_min_c:7, temperature_max_c:14, precipitation_total_mm:1
}));
let html = "";
const buttons = [7,14].map(n=>({
  dataset:{days:String(n)},
  addEventListener(_type,handler){this.handler=handler},
  focus(){}
}));
const target = {
  dataset:{},
  get innerHTML(){return html},
  set innerHTML(value){html=value},
  querySelectorAll(selector){return selector==="[data-days]"?buttons:[]},
  querySelector(selector){return buttons.find(b=>selector.includes(b.dataset.days)) || null}
};
daily.render(target, rows, "ecmwf_aifs");
assert.match(html, /14 available days/);
assert.match(html, /data-days="7" aria-pressed="true"/);
assert.match(html, /data-days="14" aria-pressed="false"/);
assert.doesNotMatch(html, /data-days="14"[^>]*disabled/);
buttons[1].handler();
assert.match(html, /data-days="14" aria-pressed="true"/);
assert.equal((html.match(/class="trend-day/g)||[]).length,14);
"""
    result = subprocess.run(["node","-e",script,str(STATIC / "daily_trend.js")],
                            capture_output=True,text=True,check=False)
    assert result.returncode == 0, result.stderr


def test_next_days_shows_full_forecast_model_at_a_glance() -> None:
    app = (STATIC / "app.js").read_text()
    index = (STATIC / "index.html").read_text()
    css = (STATIC / "accepted_ui.css").read_text()
    worker = (STATIC / "sw.js").read_text()
    assert 'ecmwf_aifs: "ECMWF AIFS"' in app
    assert 'const modelName = MODEL_LABELS[provider] || selected[0]?.model_name || provider || "Provider unavailable";' in app
    assert 'qs("#dailyProvider").textContent = provider ? `Model: ${modelName}` : "Model: unavailable";' in app
    assert 'id="dailyProvider" class="source-label daily-model-label" aria-label="Forecast model"' in index
    assert "html[data-ui-theme] .daily-model-label" in css
    assert 'href="/static/accepted_ui.css?v=58"' in index
    assert '"/static/accepted_ui.css?v=58"' in worker
    assert '"/static/daily_trend.js?v=58"' in worker
    assert '"/static/app.js?v=58"' in worker


def test_next_days_model_picker_is_native_and_provider_attributed() -> None:
    html = (STATIC / "index.html").read_text()
    app = (STATIC / "app.js").read_text()
    css = (STATIC / "accepted_ui.css").read_text()
    daily = (STATIC / "daily_trend.js").read_text()
    worker = (STATIC / "sw.js").read_text()
    assert '<label for="dailyModelSelect">Compare model</label>' in html
    assert '<select id="dailyModelSelect" aria-label="Daily forecast model" disabled>' in html
    assert '<option value="auto">Auto</option>' in html
    assert 'requestedDailyModel = "auto"' in app
    assert 'window.RozkalnsDailyTrend.availableProviders(rows, localDateKey(), PROVIDER_PREFERENCE)' in app
    assert 'const provider = requestedDailyModel === "auto" ? automaticProvider : requestedDailyModel;' in app
    assert 'qs("#dailyModelSelect").addEventListener("change", (event) => {' in app
    assert 'renderDaily(latestDailyResult, latestDailyHealthMap);' in app
    assert 'html[data-ui-theme] #dailyModelSelect' in css
    assert '"/static/daily_trend.js?v=58"' in worker
    assert '"/static/app.js?v=58"' in worker
    assert 'target.dataset.days = String(limit);' in daily


def test_daily_model_selection_respects_actual_coverage_and_horizon() -> None:
    if not shutil.which("node"):
        pytest.skip("Node.js is not installed")
    script = r"""
const assert = require("node:assert/strict");
const daily = require(process.argv[1]);
const preferred = ["weathernext3", "icon_d2", "ecmwf_ifs", "ecmwf_aifs"];
const rows = (provider,count) => Array.from({length:count},(_,i)=>({
  provider,
  date:new Date(Date.UTC(2026,9,10+i)).toISOString().slice(0,10),
  temperature_min_c:7,temperature_max_c:14,precipitation_total_mm:1
}));
const all = [...rows("icon_d2",3),...rows("ecmwf_ifs",11),...rows("ecmwf_aifs",15)];
const choices = daily.availableProviders(all,"2026-10-10",preferred);
assert.deepEqual(choices,[
  {provider:"ecmwf_aifs",days:15},
  {provider:"ecmwf_ifs",days:11},
  {provider:"icon_d2",days:3}
]);
assert.equal(daily.chooseProvider(all,"2026-10-10",preferred),"ecmwf_aifs");
const withInvalid = [...all,{provider:"weathernext3",date:"2026-10-10",temperature_min_c:null,temperature_max_c:null}];
assert.equal(daily.availableProviders(withInvalid,"2026-10-10",preferred).some(x=>x.provider==="weathernext3"),false);
let html = "";
const buttons = [7,14].map(n=>({dataset:{days:String(n)},addEventListener(_type,handler){this.handler=handler},focus(){}}));
const target = {
  dataset:{},get innerHTML(){return html},set innerHTML(value){html=value},
  querySelectorAll(selector){return selector==="[data-days]"?buttons:[]},
  querySelector(selector){return buttons.find(b=>selector.includes(b.dataset.days))||null}
};
daily.render(target, all, "ecmwf_aifs");
assert.equal(target.dataset.provider,"ecmwf_aifs");
buttons[1].handler();
assert.equal(target.dataset.days,"14");
assert.equal((html.match(/class="trend-day/g)||[]).length,14);
daily.render(target, all, "ecmwf_ifs");
assert.equal(target.dataset.provider,"ecmwf_ifs");
assert.equal(target.dataset.days,"14");
assert.equal((html.match(/class="trend-day/g)||[]).length,11);
daily.render(target, all, "icon_d2");
assert.equal(target.dataset.provider,"icon_d2");
assert.equal(target.dataset.days,"7");
assert.match(html,/data-days="14"[^>]*disabled/);
assert.equal((html.match(/class="trend-day/g)||[]).length,3);
"""
    result = subprocess.run(
        ["node", "-e", script, str(STATIC / "daily_trend.js")],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr



def test_next_days_compact_model_control_integrates_with_card() -> None:
    html = (STATIC / "index.html").read_text()
    css = (STATIC / "accepted_ui.css").read_text()
    app = (STATIC / "app.js").read_text()
    assert '<div class="section-heading next-days-heading">' in html
    section = html.split('<div class="section-heading next-days-heading">', 1)[1].split(
        '<div id="dailyState"', 1
    )[0]
    assert section.index('id="nextDaysTitle"') < section.index('id="dailyModelSelect"')
    assert section.index('id="dailyModelSelect"') < section.index('class="section-chevron"')
    assert 'html[data-ui-theme] .next-days-heading .daily-model-controls' in css
    assert 'flex:0 1 195px;' in css
    assert 'min-height:44px;' in css
    assert 'background:var(--card);' in css
    assert 'html[data-ui-theme] .next-days-heading .daily-model-label' in css
    assert 'background:transparent;' in css
    assert 'picker.innerHTML = \'<option value="auto">Auto</option>\'' in app
    assert '${days}d</option>' in app
