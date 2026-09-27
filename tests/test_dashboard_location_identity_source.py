from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"


def test_public_benchmark_does_not_replace_dashboard_location_identity() -> None:
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    provenance = (STATIC / "provenance_v1.js").read_text(encoding="utf-8")
    index = (STATIC / "index.html").read_text(encoding="utf-8")

    assert 'heroLabel: "Dortmund-Wickede · reference"' in app
    assert 'station_05480: "Dortmund-Wickede · reference"' in provenance
    assert 'current.cloneNode(true)' in provenance
    assert 'queueMicrotask(applyDashboardLocationIdentity)' in provenance
    assert index.index('/static/weather_ui.js') < index.index('/static/provenance_v1.js')


def test_werl_is_observation_provenance_not_dashboard_identity() -> None:
    provenance = (STATIC / "provenance_v1.js").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert 'source.textContent = `Observation source · ${truthSource}${sourceLocation}`;' in provenance
    assert 'setSourceData(source, "sourceLocationLabel", current?.location?.label);' in provenance
    assert 'HOME_LABEL=Dortmund-Wickede' in env_example
