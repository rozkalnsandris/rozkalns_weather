from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"
APP_JS = STATIC / "app.js"
WEATHER_UI_JS = STATIC / "weather_ui.js"


def test_station_05480_dashboard_identity_stays_dortmund_wickede() -> None:
    app_source = APP_JS.read_text()
    weather_ui_source = WEATHER_UI_JS.read_text()

    canonical_label = 'Dortmund-Wickede · reference'

    assert f'heroLabel: "{canonical_label}"' in app_source
    assert f'station_05480: "{canonical_label}"' in weather_ui_source
    assert 'station_05480: "DWD CDC Werl 05480 · reference"' not in weather_ui_source


def test_werl_remains_observation_benchmark_not_dashboard_identity() -> None:
    app_source = APP_JS.read_text()

    # Werl may remain visible as DWD observation provenance. It must not replace
    # the dashboard/home-facing location identity.
    assert 'current.location?.label || "Werl"' in app_source
    assert 'heroLabel: "Dortmund-Wickede · reference"' in app_source
