from pathlib import Path


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

    assert 'station_05480: "DWD CDC Werl 05480 · reference"' in source
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


def test_pwa_cache_is_versioned_and_old_weather_caches_are_deleted_on_activate() -> None:
    source = (STATIC / "sw.js").read_text()
    assert 'const CACHE = "rozkalns-weather-v9"' in source
    assert '"/static/weather_ui.js"' in source
    assert '"/static/consumer_ui.js"' in source
    assert 'self.addEventListener("activate"' in source
    assert "caches.keys()" in source
    assert "caches.delete(name)" in source
    assert "name.startsWith(CACHE_PREFIX)" in source


def test_visual_acceptance_fixture_declares_required_states_and_viewports() -> None:
    fixture = (ROOT / "tests" / "fixtures" / "weather_visual_states.html").read_text()
    docs = (ROOT / "docs" / "WEATHER_CONDITIONS.md").read_text()
    for condition in ("clear", "partly_cloudy", "rain", "thunderstorm", "unknown"):
        assert condition in fixture
    assert '"night"' in fixture
    assert "1440x900" in docs
    assert "412x892" in docs
