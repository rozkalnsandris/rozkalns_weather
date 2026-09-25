from pathlib import Path


ROOT = Path(__file__).parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"
INDEX = STATIC / "index.html"
APP = STATIC / "app.js"
CONSUMER_UI = STATIC / "consumer_ui.js"
SERVICE_WORKER = STATIC / "sw.js"


def test_consumer_ui_helper_loads_after_native_weather_ui_and_is_cached() -> None:
    html = INDEX.read_text()
    worker = SERVICE_WORKER.read_text()

    assert html.index('/static/weather_ui.js') < html.index('/static/consumer_ui.js')
    assert html.index('/static/consumer_ui.js') < html.index('/static/runtime_badge.js')
    assert '"/static/consumer_ui.js"' in worker
    assert 'const CACHE = "rozkalns-weather-v6"' in worker


def test_next_hours_has_one_deterministic_now_slot_and_keeps_local_labels() -> None:
    source = CONSUMER_UI.read_text()

    assert "const NOW_WINDOW_MS = 45 * 60 * 1000" in source
    assert "if (distance > NOW_WINDOW_MS) return" in source
    assert "candidate.distance < best.distance" in source
    assert "candidate.distance === best.distance && candidate.future && !best.future" in source
    assert "const isNow = index === nowIndex" in source
    assert 'label.textContent = isNow ? "Now" : berlinLocalTime(row.valid_time_utc)' in source
    assert 'timeZone: "Europe/Berlin"' in source
    assert "card.dataset.validTimeUtc = row.valid_time_utc" in source
    assert "baseRenderConsumerHourly(tempResult, precipResult, healthMap)" in source


def test_identical_consumer_status_is_hidden_but_distinct_states_are_restored() -> None:
    source = CONSUMER_UI.read_text()
    app = APP.read_text()

    assert 'dedupeSurfacePair("overviewTempState", "overviewPrecipState")' in source
    assert 'dedupeSurfacePair("providerState", "networkState")' in source
    assert "surfaceSignature(primary) !== surfaceSignature(duplicate)" in source
    assert "restoreSurface(duplicateId)" in source
    assert "window.setSurfaceState = function setSurfaceStateWithDedupReset" in source
    assert 'duplicate.setAttribute("aria-hidden", "true")' in source
    assert 'duplicate.removeAttribute("role")' in source
    assert 'duplicate.removeAttribute("aria-live")' in source

    # Distinct variable failures remain separate evidence in the base renderer.
    assert "Temperature forecast unavailable" in app
    assert "Precipitation forecast unavailable" in app
