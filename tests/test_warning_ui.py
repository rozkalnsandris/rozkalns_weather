from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "src/rozkalns_weather/static/index.html"
RUNTIME = ROOT / "src/rozkalns_weather/static/runtime_badge.js"


def test_warning_ui_keeps_dwd_authority_and_explicit_states() -> None:
    html = INDEX.read_text()
    source = RUNTIME.read_text()
    assert 'id="overviewWarningState"' in html
    assert 'id="warningsState"' in html
    assert "DWD official warnings" in html
    assert 'fetch("/api/warnings", { cache: "no-store" })' in source
    assert "warningEvidence" in source
    assert "loading" in source
    assert "active" in source
    assert "stale" in source
    assert "error" in source


def test_warning_payload_is_human_readable_with_diagnostics_separate() -> None:
    source = RUNTIME.read_text()
    assert "function warningReadableText(model, error = null)" in source
    assert 'summary.textContent = "Technical warning JSON"' in source
    assert "Affected area" not in source
