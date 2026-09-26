from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"


def _consumer_source() -> str:
    return (STATIC / "consumer_ui.js").read_text()


def test_consumer_overlay_keeps_current_temperature_explicitly_observational() -> None:
    source = _consumer_source()
    index = (STATIC / "index.html").read_text()

    assert index.index('/static/weather_ui.js') < index.index('/static/consumer_ui.js')
    assert 'DWD observation · ${berlinLocalTime(observed)} · Europe/Berlin' in source
    assert 'state.classList.add("compact-state")' in source
    assert 'FRESH · DWD observation · ${ageLabel}' in source
    assert 'STALE · DWD observation ${localTime} · not current' in source
    assert 'OFFLINE · last DWD observation ${localTime} · not current' in source
    assert 'document.querySelector("#heroTemperature")' not in source


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
