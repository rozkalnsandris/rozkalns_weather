from pathlib import Path
import re


ROOT = Path(__file__).parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"


def test_native_weather_ui_is_loaded_after_base_app_and_has_no_weather_emoji_dependency() -> None:
    index = (STATIC / "index.html").read_text()
    source = (STATIC / "weather_ui.js").read_text()
    assert index.index('/static/app.js') < index.index('/static/weather_ui.js')
    assert 'id="heroIcon" class="hero-weather-icon" aria-hidden="true"></div>' in index
    for glyph in ("☀", "🌤", "☁️", "🌧", "🌦"):
        assert glyph not in source
    assert "window.renderCurrent =" in source
    assert "window.renderConsumerHourly =" in source
    assert "window.renderDaily =" in source


def test_original_svg_family_covers_required_condition_groups_and_accessibility_modes() -> None:
    source = (STATIC / "weather_ui.js").read_text()
    for condition in (
        "clear",
        "mostly_clear",
        "partly_cloudy",
        "overcast",
        "fog",
        "drizzle",
        "freezing_precipitation",
        "rain",
        "heavy_rain",
        "snow",
        "thunderstorm",
        "thunderstorm_hail",
        "unknown",
    ):
        assert condition in source
    assert 'role="img" aria-label=' in source
    assert 'aria-hidden="true" focusable="false"' in source
    assert "xmlns=\"http://www.w3.org/2000/svg\"" in source


def test_theme_uses_provider_daylight_before_explicit_timezone_fallback() -> None:
    source = (STATIC / "weather_ui.js").read_text()
    assert '"provider_is_day"' in source
    assert '"timezone-hour-fallback-v1"' in source
    assert "weather-theme-day" in source
    assert "weather-theme-night" in source
    assert "sameRun(anchor, dayRow)" in source
    assert "body.weather-theme-day" in source
    assert "body.weather-theme-night" in source


def test_public_reference_identity_and_unknown_observation_semantics_are_explicit() -> None:
    source = (STATIC / "weather_ui.js").read_text()
    observed = source.split("function observedCondition(items)", 1)[1].split("function renderObservedIcon", 1)[0]

    assert 'station_05480: "Dortmund-Wickede · reference"' in source
    assert 'station_05480: "DWD CDC Werl 05480 · reference"' not in source
    assert "PUBLIC_REFERENCE_PRESENTATION[selector.value]" in source
    assert "applyForecastLocationIdentity()" in source
    assert "MutationObserver" in source
    assert "Condition unavailable from current observation" in observed
    assert '["precipitation_1h", "cloud_cover"]' in observed
    assert "fallbackCondition(precip, cloudCover)" in observed
    assert "loadVariable" not in observed
    assert "weather_code" not in observed
    assert 'source: "insufficient_condition_evidence"' in observed
    assert "HOME_LAT" not in source
    assert "HOME_LON" not in source


def test_pwa_cache_is_versioned_complete_and_atomically_activated() -> None:
    source = (STATIC / "sw.js").read_text()
    index = (STATIC / "index.html").read_text()
    app = (STATIC / "app.js").read_text()
    observation = (STATIC / "observation_age.js").read_text()
    lifecycle = (STATIC / "pwa_lifecycle.js").read_text()

    assert 'const CACHE = "rozkalns-weather-v29"' in source
    shell_assets = set(re.findall(r'"(/static/[^"?]+)"', source))
    index_assets = set(re.findall(r'(?:src|href)="(/static/[^"?]+)"', index))
    assert index_assets <= shell_assets

    for asset in (
        "/static/navigation_v1.js",
        "/static/weather_ui.js",
        "/static/consumer_ui.js",
        "/static/observation_age.js",
        "/static/forecast_loading.js",
        "/static/request_lifecycle.js",
        "/static/pwa_lifecycle.js",
        "/static/radar_timeline.js",
        "/static/status_v1.js",
        "/static/runtime_badge.js",
        "/static/accuracy_v3.js",
        "/static/provenance_v1.js",
    ):
        assert asset in shell_assets

    assert 'navigator.serviceWorker.register("/sw.js", { scope: "/" })' in app
    assert 'navigator.serviceWorker.register("/static/sw.js")' not in app
    assert 'siblingScriptUrl("pwa_lifecycle.js")' in observation
    assert "self.skipWaiting()" in source
    assert "self.clients.claim()" in source
    assert "SHELL_PATHS.has(url.pathname)" in source
    assert 'cache.match(event.request, { ignoreSearch: true })' in source
    assert "event.respondWith(fetch(event.request));" in source
    assert "caches.keys()" in source
    assert "caches.delete(name)" in source
    assert "name.startsWith(CACHE_PREFIX)" in source
    assert 'navigator.serviceWorker.addEventListener("controllerchange", () =>' in lifecycle
    assert "void reloadForUpdatedWorker();" in lifecycle
    assert "window.location.reload()" in lifecycle


def test_visual_acceptance_fixture_declares_required_states_and_viewports() -> None:
    fixture = (ROOT / "tests" / "fixtures" / "weather_visual_states.html").read_text()
    docs = (ROOT / "docs" / "WEATHER_CONDITIONS.md").read_text()
    for condition in ("clear", "partly_cloudy", "rain", "thunderstorm", "unknown"):
        assert condition in fixture
    assert '"night"' in fixture
    assert "1440x900" in docs
    assert "412x892" in docs
