from pathlib import Path

from fastapi.testclient import TestClient

from rozkalns_weather.app import create_app
from rozkalns_weather.config import Settings
from rozkalns_weather.db import Database


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "src/rozkalns_weather/static/index.html"
APP_JS = ROOT / "src/rozkalns_weather/static/app.js"
APP_CSS = ROOT / "src/rozkalns_weather/static/app.css"
UI_DOC = ROOT / "docs/UI.md"
REFERENCE = ROOT / "docs/ui/consumer-weather-overview-reference-v1.webp"


def _client(tmp_path) -> TestClient:
    settings = Settings.from_env({"DATABASE_URL": f"sqlite:///{tmp_path / 'weather.db'}"})
    return TestClient(create_app(settings=settings, database=Database(settings.database_url)))


def test_canonical_reference_and_weather_first_overview_are_locked() -> None:
    html = INDEX.read_text()
    docs = UI_DOC.read_text()

    assert REFERENCE.exists()
    assert "consumer-weather-overview-reference-v1.webp" in docs
    for surface_id in (
        "heroTemperature",
        "heroCondition",
        "heroUpdated",
        "hourlyStrip",
        "consumerHourlyChart",
        "dailyGrid",
        "detailHumidity",
        "detailWind",
        "detailPressure",
        "detailRain",
        "detailCloud",
        "detailGust",
        "modelSnapshot",
        "overviewWarningState",
    ):
        assert f'id="{surface_id}"' in html

    assert html.index('id="heroTemperature"') < html.index('id="hourlyStrip"')
    assert html.index('id="hourlyStrip"') < html.index('id="dailyGrid"')
    assert html.index('id="dailyGrid"') < html.index('id="modelSnapshot"')


def test_current_observation_never_turns_stale_station_truth_into_now(tmp_path) -> None:
    client = _client(tmp_path)
    script = client.get("/static/app.js").text

    assert 'OBSERVATION_FRESH_HOURS = 3' in script
    assert 'timeZone: "Europe/Berlin"' in script
    assert "it is not labelled as current-now" in script
    assert "Latest observation" in script
    assert 'apiWithFallback("/api/current", "current")' in script
    assert "forecast fallback" not in script.lower()

    for variable in (
        "temperature_2m",
        "relative_humidity_2m",
        "wind_speed_10m",
        "pressure_msl",
        "precipitation_1h",
        "cloud_cover",
        "wind_gust_10m",
    ):
        assert variable in script


def test_next_hours_and_days_use_attributed_provider_values_without_combined() -> None:
    html = INDEX.read_text()
    script = APP_JS.read_text()

    assert 'id="hourlyProvider"' in html
    assert 'id="dailyProvider"' in html
    assert 'precipitation shown as amount (mm), not probability' in script
    assert 'min/max and precipitation total' in script
    assert 'chooseProvider(tempRows, precipRows)' in script
    assert 'chooseProvider(rows)' in script
    assert 'data-provider="${escapeHtml(provider)}"' in script
    assert "Combined" not in html
    assert "fabricated Combined" not in script


def test_model_snapshot_keeps_weathernext_pending_instead_of_fabricating_values() -> None:
    html = INDEX.read_text()
    script = APP_JS.read_text()

    for label in ("WeatherNext 3", "ICON-D2", "ECMWF IFS", "AIFS"):
        assert label in html
    assert 'MODEL_SNAPSHOT_IDS = ["weathernext3", "icon_d2", "ecmwf_ifs", "ecmwf_aifs"]' in script
    assert 'No genuine data · pending' in script
    assert 'const value = row && Number.isFinite(Number(row.value)) ? `${Number(row.value).toFixed(1)}°` : "—"' in script
    assert "waiting for at least two genuine model values" in script


def test_consumer_navigation_and_mobile_layout_match_approved_information_architecture() -> None:
    html = INDEX.read_text()
    css = APP_CSS.read_text()

    for view, label in (
        ("overview", "Overview"),
        ("models", "Models"),
        ("safety", "Radar"),
        ("accuracy", "Accuracy"),
        ("status", "Status"),
    ):
        assert f'data-view="{view}"' in html
        assert f"<small>{label}</small>" in html

    assert "@media(max-width:560px)" in css
    assert "@media(max-width:380px)" in css
    assert ".bottom-nav{position:fixed" in css
    assert ".hourly-strip{display:grid;grid-auto-flow:column" in css
    assert ".details-grid{display:grid" in css


def test_dwd_warning_summary_only_claims_no_active_warnings_from_fresh_official_response() -> None:
    html = INDEX.read_text()
    script = APP_JS.read_text()

    assert 'data-warning-authority="DWD"' in html
    assert "DWD official warnings" in html
    assert 'if (stateFromResult(result) !== "fresh")' in script
    assert 'payload.state === "no_active_alerts"' in script
    assert "No active warnings · current DWD response" in script
    assert "Cached warning response · not current official status" in script
