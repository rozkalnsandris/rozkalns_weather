from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "src/rozkalns_weather/static/index.html"
TIME_JS = ROOT / "src/rozkalns_weather/static/time_semantics.js"
SERVICE_WORKER = ROOT / "src/rozkalns_weather/static/sw.js"
DOC = ROOT / "docs/TIMEZONE_DST_SEMANTICS.md"


def test_pwa_loads_dst_contract_after_existing_renderers() -> None:
    html = INDEX.read_text()
    assert '/static/time_semantics.js' in html
    assert html.index('/static/app.js') < html.index('/static/accuracy_v3.js')
    assert html.index('/static/accuracy_v3.js') < html.index('/static/time_semantics.js')


def test_pwa_uses_explicit_berlin_timezone_and_offset_bearing_labels() -> None:
    script = TIME_JS.read_text()
    assert 'BERLIN_TIMEZONE = "Europe/Berlin"' in script
    assert 'timeZoneName: "shortOffset"' in script
    assert 'globalThis.formatLocalTime = formatLocalTimeBerlin' in script
    assert 'globalThis.formatTimestamp = formatTimestampBerlin' in script
    assert 'globalThis.localDateKey = localDateKeyBerlin' in script
    assert 'globalThis.berlinMonthKey = localMonthKeyBerlin' in script
    assert 'globalThis.refresh' in script
    assert 'UTC_STRING' in script


def test_dst_helper_is_part_of_offline_pwa_cache() -> None:
    worker = SERVICE_WORKER.read_text()
    assert "rozkalns-weather-v5" in worker
    assert '"/static/time_semantics.js"' in worker


def test_pwa_documentation_preserves_utc_and_explains_both_dst_edges() -> None:
    docs = DOC.read_text()
    assert "canonical storage/provenance timezone: `UTC`" in docs
    assert "Spring-forward" in docs
    assert "Autumn fallback" in docs
    assert "02:30 +02:00" in docs
    assert "02:30 +01:00" in docs
    assert "half-open UTC query intervals" in docs
    assert "production corpus migration" in docs
