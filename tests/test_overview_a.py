from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"


def test_overview_assets_are_present_and_loaded_in_order() -> None:
    html = (STATIC / "index.html").read_text()
    worker = (STATIC / "sw.js").read_text()
    for name in ("accepted_ui.css", "ui_preferences.js", "daily_trend.js"):
        assert f"/static/{name}" in html
        assert f"/static/{name}" in worker
        assert (STATIC / name).exists()
    assert html.index('/static/daily_trend.js') < html.index('/static/app.js')
