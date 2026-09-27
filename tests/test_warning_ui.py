"""Warning UI contract: auto-load official DWD state without hiding last-known evidence."""
from pathlib import Path
import subprocess


def test_warning_state_behavior():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(["node", "--test", "tests/js/warning_state.test.cjs"], cwd=root, check=True)


def test_warning_controller_auto_loads_and_is_pwa_refreshed():
    root = Path(__file__).resolve().parents[1]
    static = root / "src/rozkalns_weather/static"
    runtime = (static / "runtime_badge.js").read_text()
    worker = (static / "sw.js").read_text()
    semantics = (root / "docs/WARNING_REFRESH_SEMANTICS.md").read_text()

    assert 'fetch("/api/warnings", { cache: "no-store" })' in runtime
    assert 'void refreshWarnings();' in runtime
    assert 'data-view="safety"' in runtime
    assert 'WARNING_CACHE_KEY' in runtime
    assert 'alert.lifecycle !== "expired"' in runtime
    assert 'authority !== "DWD"' in runtime
    assert 'payload.official !== true' in runtime
    assert 'const refreshWarnings = createSingleFlight(runWarningRefresh);' in runtime
    assert 'document.addEventListener("visibilitychange"' in runtime
    assert 'document.visibilityState === "visible"' in runtime
    assert 'warningCheckedAge' in runtime
    assert '"rozkalns-weather-v13"' in worker
    assert '"/static/runtime_badge.js"' in worker
    assert "No fixed client-side freshness TTL" in semantics
    assert "`retrieved_at_utc` is the weather app's successful warning-fetch time" in semantics
    assert "not the DWD CAP publication timestamp" in semantics
