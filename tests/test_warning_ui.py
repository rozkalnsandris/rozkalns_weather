"""Warning UI contract: auto-load official DWD state without hiding last-known evidence."""
from pathlib import Path
import subprocess


def test_warning_state_behavior():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(["node", "--test", "tests/js/warning_state.test.cjs"], cwd=root, check=True)


def test_warning_controller_auto_loads_and_is_pwa_refreshed():
    static = Path(__file__).resolve().parents[1] / "src/rozkalns_weather/static"
    runtime = (static / "runtime_badge.js").read_text()
    worker = (static / "sw.js").read_text()

    assert 'fetch("/api/warnings", { cache: "no-store" })' in runtime
    assert 'void refreshWarnings();' in runtime
    assert 'data-view="safety"' in runtime
    assert 'WARNING_CACHE_KEY' in runtime
    assert 'alert.lifecycle !== "expired"' in runtime
    assert 'authority !== "DWD"' in runtime
    assert 'payload.official !== true' in runtime
    assert '"rozkalns-weather-v12"' in worker
    assert '"/static/runtime_badge.js"' in worker
