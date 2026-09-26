from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"


def _consumer_source() -> str:
    return (STATIC / "consumer_ui.js").read_text()


def test_consumer_overlay_keeps_current_temperature_explicitly_observational() -> None:
    source = _consumer_source()
    index = (STATIC / "index.html").read_text()

    assert index.index('/static/weather_ui.js') < index.index('/static/consumer_ui.js')
    assert 'heroUpdated.textContent = observed' in source
    assert 'Observed ${localTime} · ${ageLabel}' in source
    assert 'heroFeels.textContent = "DWD observation"' in source
    assert 'state.textContent = "DWD observation current"' in source
    assert 'state.hidden = true' in source
    assert 'state.setAttribute("aria-hidden", "true")' in source
    assert 'FRESH · DWD observation' not in source
    assert 'STALE · DWD observation is not current' in source
    assert 'ERROR · DWD observation provider degraded' in source
    assert 'OFFLINE · showing last DWD observation · not current' in source
    assert 'document.querySelector("#heroTemperature")' not in source


def test_normal_observation_age_is_visible_once_and_degraded_state_keeps_warning_surface() -> None:
    source = _consumer_source()

    assert source.count('Observed ${localTime} · ${ageLabel}') == 1
    assert 'const ageLabel = ageMinutes == null ? "age unknown"' in source
    assert '`${ageMinutes} min ago`' in source
    assert 'if (heroUpdated && state?.dataset.state === "fresh")' in source
    assert 'else if (state.dataset.state === "stale")' in source
    assert 'else if (state.dataset.state === "error")' in source
    assert 'else if (state.dataset.state === "offline")' in source
    assert 'observed_at_utc}' not in source


def test_fresh_hero_state_is_non_rendered_and_source_identity_is_single() -> None:
    index = (STATIC / "index.html").read_text()

    assert '.hero-state[hidden]{display:none}' in index
    assert index.count('id="heroSource"') == 1
    assert '<span id="heroSource">Werl · official DWD observation source</span>' in index
    assert 'DWD CDC 05480 reference observation</span>' not in index
    assert '.hero-source-row #heroSource{text-align:left}' in index


def test_forecast_condition_fallback_reuses_the_canonical_now_card_and_stays_labelled() -> None:
    source = _consumer_source()

    assert 'window.chooseProvider(tempRows, precipRows)' in source
    assert 'window.canonicalProviderRows(tempRows, provider)' in source
    assert 'const nowIndex = selectNowIndex(tempSeries, Date.now())' in source
    assert 'if (heroIcon.dataset.condition && heroIcon.dataset.condition !== "unknown") return true' in source
    assert 'const condition = card?.dataset.condition' in source
    assert 'if (!row || !card || !condition || condition === "unknown") return false' in source
    assert 'const label = `${visibleCondition} · ${modelName} forecast`' in source
    assert 'heroIcon.dataset.conditionEvidence = "forecast"' in source
    assert 'heroIcon.dataset.conditionSource = conditionSource' in source
    assert 'heroIcon.dataset.forecastProvider = provider || "unknown"' in source
    assert 'heroIcon.dataset.forecastValidTimeUtc = row.valid_time_utc || ""' in source
    assert 'heroIcon.dataset.forecastInitTimeUtc = row.init_time_utc || ""' in source
    assert 'heroIcon.dataset.forecastRetrievedAtUtc = row.retrieved_at_utc || ""' in source
    assert 'loadVariable(' not in source
    assert 'HOME_LAT' not in source
    assert 'HOME_LON' not in source


def test_daily_high_low_is_explicitly_forecast_data() -> None:
    source = _consumer_source()

    assert 'const baseRenderDaily = window.renderDaily' in source
    assert 'highLow.textContent = `Today forecast · ${highLow.textContent}`' in source


def test_unknown_observation_is_not_relabelled_without_a_valid_now_forecast_condition() -> None:
    source = _consumer_source()

    assert 'if (nowIndex < 0) return false' in source
    assert 'condition === "unknown"' in source
    assert 'conditionEvidence = heroIcon.dataset.condition === "unknown"' in source
    assert '"observation-unavailable"' in source


def test_overview_static_change_advances_the_pwa_shell_cache() -> None:
    service_worker = (STATIC / "sw.js").read_text()

    assert 'const CACHE = "rozkalns-weather-v9"' in service_worker
    assert '"/static/consumer_ui.js"' in service_worker
