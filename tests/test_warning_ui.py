from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "src/rozkalns_weather/static/index.html"
RUNTIME = ROOT / "src/rozkalns_weather/static/runtime_badge.js"
JS_TEST = ROOT / "tests/js/warning_state.test.cjs"
SERVICE_WORKER = ROOT / "src/rozkalns_weather/static/sw.js"


def test_warning_ui_autoloads_with_explicit_state_model() -> None:
    html = INDEX.read_text()
    source = RUNTIME.read_text()
    assert 'id="overviewWarningState"' in html
    assert 'id="warningsState"' in html
    assert "const WARNING_CACHE_KEY" in source
    assert 'fetch("/api/warnings", { cache: "no-store" })' in source
    assert "warningEvidence" in source
    assert "reduceWarningState" in source
    assert "warningSummary" in source
    assert "void refreshWarnings();" in source
    assert "loading" in source
    assert "clear" in source
    assert "active" in source
    assert "stale" in source
    assert "error" in source


def test_warning_refresh_lifecycle_is_event_driven_and_cache_safe() -> None:
    source = RUNTIME.read_text()
    worker = SERVICE_WORKER.read_text()
    assert "function createSingleFlight(task)" in source
    assert 'document.addEventListener("visibilitychange"' in source
    assert 'document.visibilityState === "visible"' in source
    assert 'window.addEventListener("online", () => { void refreshWarnings(); });' in source
    assert "warningCheckedAge" in source
    assert "No fixed client-side freshness TTL" not in source
    assert 'const CACHE = "rozkalns-weather-v19"' in worker


def test_warning_primary_surface_is_readable_and_raw_json_is_diagnostics_only() -> None:
    source = RUNTIME.read_text()
    assert "function warningReadableText(model, error = null)" in source
    assert 'output.textContent = warningReadableText(model, error);' in source
    assert 'details.id = "warningsDiagnostics"' in source
    assert 'summary.textContent = "Technical warning JSON"' in source
    assert 'raw.id = "warningsDiagnosticsJson"' in source
    assert "raw.textContent = JSON.stringify(payload, null, 2);" in source
    assert "output.textContent = JSON.stringify(model.evidence.payload" not in source
    assert '`Reference location: ${warningReferenceLabel(payload)}`' in source
    assert "Affected area" not in source


def test_warning_state_behavior_node_suite() -> None:
    node = shutil.which("node")
    if node is None:
        raise AssertionError("node is required for warning-state behavior tests")
    completed = subprocess.run(
        [node, "--test", str(JS_TEST)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
