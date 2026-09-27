"""Execute the dependency-free appearance and daily trend behavior suite."""
from pathlib import Path
import subprocess


def test_overview_a_behavior():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(["node", "--test", "tests/js/overview_a.test.cjs"], cwd=root, check=True)


def test_overview_a_assets_are_available_offline():
    static = Path(__file__).resolve().parents[1] / "src/rozkalns_weather/static"
    html = (static / "index.html").read_text()
    worker = (static / "sw.js").read_text()
    for name in ("accepted_ui.css", "ui_preferences.js", "daily_trend.js"):
        assert f"/static/{name}" in html
        assert f"/static/{name}" in worker
        assert (static / name).exists()
    assert html.index('/static/daily_trend.js') < html.index('/static/app.js')
