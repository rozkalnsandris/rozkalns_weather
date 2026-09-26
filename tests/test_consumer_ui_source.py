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
    assert 'const CACHE = "rozkalns-weather-v9"' in worker


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


def test_provider_ui_semantics_keep_pending_inactive_lagging_and_error_distinct() -> None:
    source = CONSUMER_UI.read_text()
    app = APP.read_text()

    error_rule = 'if (freshness === "error" || ingest === "error" || provider?.state === "error") return "error";'
    pending_rule = 'if (["access_pending", "pending"].includes(freshness) || ["access_pending", "pending"].includes(ingest)) return "pending";'
    inactive_rule = '["not_tracked", "inactive"].includes(freshness)'
    fresh_rule = 'if (freshness === "fresh") return "fresh";'
    stale_rule = '["lagging", "degraded", "stale", "unknown", "not_ingested"].includes(freshness)'

    for rule in (error_rule, pending_rule, inactive_rule, fresh_rule, stale_rule):
        assert rule in source

    # Precedence is the behavioral contract: an ingest error wins; access pending
    # wins over the simultaneous not-tracked marker; otherwise not-tracked is inactive.
    assert source.index(error_rule) < source.index(pending_rule)
    assert source.index(pending_rule) < source.index(inactive_rule)
    assert source.index(inactive_rule) < source.index(fresh_rule)
    assert source.index(fresh_rule) < source.index(stale_rule)
    assert 'provider?.reason_code === "NOT_IN_PUBLIC_RECURRING_SCOPE"' in source
    assert "provider?.tracked === false" in source
    assert 'window.normalizedProviderState = normalizedProviderUiState' in source
    assert "normalizedProviderUiState," in source

    # The recurring public summary remains scoped to its canonical provider set.
    public_scope = app.split("const PUBLIC_PROVIDER_IDS", 1)[1].split("]);", 1)[0]
    for provider in ('"dwd_observations"', '"dwd_mosmix_l"', '"icon_d2"', '"ecmwf_ifs"', '"ecmwf_aifs"'):
        assert provider in public_scope
    assert '"weathernext3"' not in public_scope
    assert 'filter((provider) => PUBLIC_PROVIDER_IDS.has(provider.id))' in app
    assert 'tracked.filter((provider) => normalizedProviderState(provider) !== "fresh")' in app

    # Card text carries the state independently of color, while raw provenance remains visible.
    assert 'class="state-chip state-${uiState}">${uiState}</span>' in app
    assert 'ingest ${escapeHtml(provider.ingest_state || provider.state || "unknown")}' in app
    assert 'freshness ${escapeHtml(provider.freshness_state || "unknown")}' in app
    assert "provider.reason_code" in app

    # WeatherNext remains first-class without inventing a value while access is pending.
    assert 'provider === "weathernext3" ? "No genuine data · pending"' in app
    assert 'const value = row && Number.isFinite(Number(row.value)) ? `${Number(row.value).toFixed(1)}°` : "—";' in app
