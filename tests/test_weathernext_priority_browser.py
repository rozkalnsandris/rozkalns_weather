from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"
PRIORITY_JS = STATIC / "model_snapshot_alignment.js"


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the WeatherNext priority proof")


def _run_browser(uri: str, *, width: int) -> str:
    completed = subprocess.run(
        [
            _browser_binary(),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            f"--window-size={width},900",
            "--virtual-time-budget=900",
            "--dump-dom",
            uri,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed.stdout


def _fixture(tmp_path: Path, *, theme: str) -> Path:
    fixture = tmp_path / f"weathernext-priority-{theme}.html"
    fixture.write_text(
        f"""<!doctype html>
<html data-ui-theme="{theme}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body>
  <section id="overview">
    <section class="weather-hero"><h1>Dortmund-Wickede</h1></section>
    <section class="consumer-panel" aria-labelledby="nextHoursTitle"><h2 id="nextHoursTitle">Next Hours</h2></section>
    <section class="consumer-panel model-snapshot-panel"><div id="modelSnapshot"></div><div id="modelSpread"></div></section>
  </section>
  <section id="models">
    <header class="subpage-header"><h1>Models</h1></header>
    <div class="panel research"><div id="providerClasses"></div></div>
    <div id="modelsTempState" data-state="loading">LOADING · model freshness</div>
  </section>
  <output id="proof"></output>
  <script>
    function renderModelSnapshot() {{}}
    function canonicalProviderRows(rows, provider) {{ return rows.filter((row) => row.provider === provider).slice().sort((a,b) => a.valid_time_utc.localeCompare(b.valid_time_utc)); }}
    function futureRows(rows, count) {{ return rows.slice(0, count); }}
    function formatLocalTime(value) {{ return new Intl.DateTimeFormat('en-GB', {{timeZone:'Europe/Berlin',hour:'2-digit',minute:'2-digit'}}).format(new Date(value)); }}
    function escapeHtml(value) {{ return String(value ?? ''); }}
  </script>
  <script src="{PRIORITY_JS.as_uri()}"></script>
  <script>
    const proof = document.getElementById('proof');
    const cards = () => [...document.querySelectorAll('[data-weathernext-priority]')];
    proof.dataset.initialLoading = String(cards().length === 2 && cards().every((card) => card.dataset.state === 'loading'));
    proof.dataset.overviewOrder = String(document.querySelector('#overview').children[1]?.dataset.weathernextPriority === 'overview');
    proof.dataset.modelsOrder = String(document.querySelector('#models').children[1]?.dataset.weathernextPriority === 'models');

    const genuineRows = [
      {{provider:'weathernext3', model_name:'WeatherNext 3', model_version:'wn3-2026-09', init_time_utc:'2026-10-01T00:00:00Z', retrieved_at_utc:'2026-10-01T01:00:00Z', valid_time_utc:'2026-10-01T12:00:00Z', lead_hours:12, statistic:'mean', value:12.5}},
      {{provider:'icon_d2', model_name:'ICON-D2', model_version:'2026-09', init_time_utc:'2026-10-01T00:00:00Z', retrieved_at_utc:'2026-10-01T01:00:00Z', valid_time_utc:'2026-10-01T12:00:00Z', lead_hours:12, statistic:'deterministic', value:11.0}},
      {{provider:'ecmwf_aifs', model_name:'AIFS', model_version:'2026-09', init_time_utc:'2026-10-01T00:00:00Z', retrieved_at_utc:'2026-10-01T01:00:00Z', valid_time_utc:'2026-10-01T12:00:00Z', lead_hours:12, statistic:'deterministic', value:11.8}}
    ];
    const freshHealth = {{weathernext3:{{ingest_state:'ready', freshness_state:'fresh'}}}};
    window.renderModelSnapshot(genuineRows, freshHealth);
    const freshText = cards()[0].textContent;
    proof.dataset.genuineValue = String(cards().every((card) => card.querySelector('.wn-value')?.textContent === '12.5°'));
    proof.dataset.provenance = String(freshText.includes('valid 2026-10-01T12:00:00Z') && freshText.includes('init 2026-10-01T00:00:00Z') && freshText.includes('lead 12 h') && freshText.includes('retrieved 2026-10-01T01:00:00Z') && freshText.includes('statistic mean') && freshText.includes('model version wn3-2026-09'));
    proof.dataset.separateReadiness = String(freshText.includes('verification readiness') && freshText.includes('DWD warning authority'));
    proof.dataset.exactComparison = String(document.getElementById('modelSnapshot').textContent.includes('12.5°') && document.getElementById('modelSnapshot').textContent.includes('11.0°'));

    window.renderModelSnapshot(genuineRows, {{weathernext3:{{ingest_state:'ready', freshness_state:'stale'}}}});
    proof.dataset.stale = String(cards().every((card) => card.dataset.state === 'stale' && !card.querySelector('.wn-value').hidden));

    const publicOnlyRows = genuineRows.filter((row) => row.provider !== 'weathernext3');
    window.renderModelSnapshot(publicOnlyRows, {{weathernext3:{{ingest_state:'access_pending', freshness_state:'not_tracked'}}}});
    const pendingText = cards()[0].textContent;
    proof.dataset.pending = String(cards().every((card) => card.dataset.state === 'pending' && card.querySelector('.wn-value').hidden) && pendingText.includes('PENDING') && pendingText.includes('access pending') && !pendingText.includes('12.5°'));

    const tempState = document.getElementById('modelsTempState');
    tempState.dataset.state = 'error';
    tempState.textContent = 'ERROR · temperature forecast unavailable';

    setTimeout(() => {{
      proof.dataset.error = String(cards().every((card) => card.dataset.state === 'error' && card.querySelector('.wn-value').hidden));
      proof.dataset.noOverflow = String(document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);
      proof.dataset.theme = document.documentElement.dataset.uiTheme;
      proof.dataset.cardCount = String(cards().length);
      proof.dataset.ready = 'true';
    }}, 80);
  </script>
</body>
</html>"""
    )
    return fixture


def test_weathernext_priority_component_source_contract() -> None:
    source = PRIORITY_JS.read_text()
    assert 'data-weathernext-priority' in source
    assert 'Primary research model' in source
    assert 'Forecast availability is being checked from current provider evidence.' in source
    assert 'WeatherNext forecast availability is separate from verification readiness and DWD warning authority.' in source
    assert 'row.lead_hours' in source
    assert 'row.retrieved_at_utc' in source
    assert 'row.model_version' in source
    assert 'root.document.querySelector("#modelSnapshot")' in source
    assert 'typeof root.qs' not in source


def test_weathernext_priority_component_states_provenance_and_required_viewports(tmp_path: Path) -> None:
    for width, theme in ((412, "light"), (1440, "dark")):
        rendered = _run_browser(_fixture(tmp_path, theme=theme).as_uri(), width=width)
        for attribute in (
            "initial-loading",
            "overview-order",
            "models-order",
            "genuine-value",
            "provenance",
            "separate-readiness",
            "exact-comparison",
            "stale",
            "pending",
            "error",
            "no-overflow",
            "ready",
        ):
            assert f'data-{attribute}="true"' in rendered, rendered
        assert 'data-card-count="2"' in rendered, rendered
        assert f'data-theme="{theme}"' in rendered, rendered
