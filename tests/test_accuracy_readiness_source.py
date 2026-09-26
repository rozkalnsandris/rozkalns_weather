from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"
ACCURACY = STATIC / "accuracy_v3.js"
APP = STATIC / "app.js"
INDEX = STATIC / "index.html"


def test_accuracy_ui_gates_clean_benchmark_on_verification_readiness() -> None:
    source = ACCURACY.read_text()

    assert "summary.verification_ready === true" in source
    assert "NOT READY · INCOMPLETE TRUTH" in source
    assert "preliminary descriptive evidence, not a clean benchmark" in source
    assert "TEMPERATURE_COVERAGE_GAP" in source
    assert "Temperature truth has coverage gaps." in source
    assert 'accuracyPanelTitle("DWD CDC 05480 verification evidence · preliminary")' in source
    assert 'accuracyPanelTitle("DWD CDC 05480 station benchmark · deterministic")' in source
    assert 'Lead-bucket aggregates are hidden until verification_ready=true.' in source


def test_accuracy_ui_has_explicit_accessible_loading_error_and_race_guard() -> None:
    source = ACCURACY.read_text()

    assert "let accuracyRequestSequence = 0;" in source
    assert "const sequence = ++accuracyRequestSequence;" in source
    assert "if (sequence !== accuracyRequestSequence) return;" in source
    assert 'setAccuracyState("loading", `LOADING · ${days}-day verification evidence is being fetched.`)' in source
    assert 'setAccuracyState("error", `ERROR · ${days}-day verification request failed: ${error}`, { alert: true })' in source
    assert 'accuracyTable.setAttribute("aria-busy", "true")' in source
    assert 'accuracyTable?.removeAttribute("aria-busy")' in source
    assert 'state.setAttribute("role", alert ? "alert" : "status")' in source
    assert 'state.setAttribute("aria-live", alert ? "assertive" : "polite")' in source


def test_accuracy_window_switch_clears_old_rows_and_uses_one_runtime_summary_controller() -> None:
    source = ACCURACY.read_text()
    app = APP.read_text()
    html = INDEX.read_text()

    assert 'accuracyTable.textContent = `Loading ${days}-day verification evidence…`' in source
    assert 'if (lead) lead.textContent = "";' in source
    assert 'globalThis.accuracy = refreshAccuracyV3;' in source
    assert 'accuracyV3Api(`/api/verification/summary?days=${days}`)' in source
    assert 'document.querySelectorAll("[data-days]")' not in source
    assert 'accuracy(Number(button.dataset.days));' in app
    assert html.index('/static/app.js') < html.index('/static/accuracy_v3.js')


def test_accuracy_status_sits_outside_scrollable_table_and_keeps_metrics_provenance() -> None:
    source = ACCURACY.read_text()

    assert 'table?.parentNode?.insertBefore(state, table)' in source
    assert 'state.className = "surface-state state-loading"' in source
    for field in ("model_version", "lead_bucket", "sample_sufficiency_state", "missingness", "mae", "rmse", "bias", "p10_p90_coverage"):
        assert field in source
