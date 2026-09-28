"""Execute exact-valid-time Model Snapshot behavior and asset wiring checks."""
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/rozkalns_weather/static"


def test_model_snapshot_alignment_behavior() -> None:
    subprocess.run(
        ["node", "--test", "tests/js/model_snapshot_alignment.test.cjs"],
        cwd=ROOT,
        check=True,
    )


def test_model_snapshot_alignment_asset_is_loaded_before_ui_overrides_and_cached() -> None:
    html = (STATIC / "index.html").read_text()
    worker = (STATIC / "sw.js").read_text()
    asset = "/static/model_snapshot_alignment.js"

    assert asset in html
    assert asset in worker
    assert (STATIC / "model_snapshot_alignment.js").exists()
    assert html.index('/static/app.js') < html.index(asset)
    assert html.index(asset) < html.index('/static/consumer_ui.js')
    assert 'const CACHE = "rozkalns-weather-v18"' in worker
