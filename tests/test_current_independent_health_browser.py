from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
OBSERVATION_AGE_JS = ROOT / "src" / "rozkalns_weather" / "static" / "observation_age.js"


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the independent-current regression proof")


def _run_browser(uri: str) -> str:
    completed = subprocess.run(
        [
            _browser_binary(),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            "--window-size=900,700",
            "--virtual-time-budget=1000",
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


def _write_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "current-independent-health.html"
    fixture.write_text(
        f"""<!doctype html>
<html><head><meta charset="utf-8"></head><body>
  <div id="heroUpdated">waiting</div>
  <div id="heroTemperature">—°</div>
  <div id="heroCondition">Loading observations…</div>
  <div id="currentState" data-state="loading">LOADING · DWD station truth</div>
  <output id="proof"></output>
  <script>
    const scenario = new URLSearchParams(location.search).get('scenario') || 'blocked';
    let currentCalls = 0;
    let renders = 0;
    let healthStarted = false;
    let lastRenderedMarker = '';

    function currentResult(label, value) {{
      return {{
        payload: {{
          observations: [{{variable:'temperature_2m', value, observed_at_utc:new Date(Date.now()-2*60*1000).toISOString()}}],
          truth_source: 'DWD CDC observations',
          location: {{label:'Dortmund-Wickede reference'}},
          marker: label,
        }},
        source: 'network',
        cached_at_utc: new Date().toISOString(),
        error: null,
      }};
    }}

    window.setSurfaceState = (id, state, message) => {{
      const element = document.getElementById(id);
      element.dataset.state = state;
      element.textContent = `${{state.toUpperCase()}} · ${{message}}`;
    }};
    window.renderCurrent = (result) => {{
      renders += 1;
      lastRenderedMarker = result.payload.marker;
      document.getElementById('currentState').dataset.state = 'fresh';
      document.getElementById('heroTemperature').textContent = `${{result.payload.observations[0].value}}°`;
      document.getElementById('heroUpdated').textContent = result.payload.marker;
    }};
    window.apiWithFallback = (url) => {{
      if (url === '/api/health/providers') {{
        healthStarted = true;
        return new Promise(() => {{}});
      }}
      if (url !== '/api/current') throw new Error(`unexpected ${{url}}`);
      currentCalls += 1;
      if (scenario === 'race') {{
        return new Promise((resolve) => setTimeout(() => resolve(currentResult('watchdog-late', 8)), 220));
      }}
      return Promise.resolve(currentResult('watchdog-current', 11));
    }};

    // Simulate the base refresh already waiting forever on health.
    void window.apiWithFallback('/api/health/providers', 'provider-health');

    if (scenario === 'fast') {{
      setTimeout(() => window.renderCurrent(currentResult('base-fast', 12), {{}}), 60);
    }}
    if (scenario === 'race') {{
      setTimeout(() => window.renderCurrent(currentResult('base-newer', 13), {{}}), 280);
    }}
  </script>
  <script src="{OBSERVATION_AGE_JS.as_uri()}"></script>
  <script>
    setTimeout(() => {{
      const proof = document.getElementById('proof');
      proof.dataset.scenario = scenario;
      proof.dataset.healthStarted = String(healthStarted);
      proof.dataset.currentCalls = String(currentCalls);
      proof.dataset.renders = String(renders);
      proof.dataset.lastRender = lastRenderedMarker;
      proof.dataset.state = document.getElementById('currentState').dataset.state;
      proof.dataset.temperature = document.getElementById('heroTemperature').textContent;
      proof.dataset.ageText = document.getElementById('heroUpdated').textContent;
      proof.dataset.ready = 'true';
    }}, 650);
  </script>
</body></html>"""
    )
    return fixture


def test_current_observation_is_not_blocked_by_provider_health(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path)

    blocked = _run_browser(f"{fixture.as_uri()}?scenario=blocked")
    assert 'data-ready="true"' in blocked, blocked
    assert 'data-health-started="true"' in blocked, blocked
    assert 'data-current-calls="1"' in blocked, blocked
    assert 'data-renders="1"' in blocked, blocked
    assert 'data-state="fresh"' in blocked, blocked
    assert 'data-temperature="11°"' in blocked, blocked
    assert 'data-last-render="watchdog-current"' in blocked, blocked
    assert 'data-age-text=' in blocked and 'Observed' in blocked and 'min ago' in blocked, blocked

    fast = _run_browser(f"{fixture.as_uri()}?scenario=fast")
    assert 'data-ready="true"' in fast, fast
    assert 'data-current-calls="0"' in fast, fast
    assert 'data-renders="1"' in fast, fast
    assert 'data-temperature="12°"' in fast, fast
    assert 'data-last-render="base-fast"' in fast, fast

    race = _run_browser(f"{fixture.as_uri()}?scenario=race")
    assert 'data-ready="true"' in race, race
    assert 'data-current-calls="1"' in race, race
    assert 'data-renders="1"' in race, race
    assert 'data-temperature="13°"' in race, race
    assert 'data-last-render="base-newer"' in race, race
