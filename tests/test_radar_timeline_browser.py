from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"
NAVIGATION = STATIC / "navigation_v1.js"
RADAR_TIMELINE = STATIC / "radar_timeline.js"
SW = STATIC / "sw.js"


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the radar timeline regression proof")


def _run_browser(uri: str, *, budget_ms: int = 1800) -> str:
    completed = subprocess.run(
        [
            _browser_binary(),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            "--window-size=900,900",
            f"--virtual-time-budget={budget_ms}",
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


def test_radar_timeline_is_lazy_cached_and_fail_closed_in_source() -> None:
    navigation = NAVIGATION.read_text()
    radar = RADAR_TIMELINE.read_text()
    worker = SW.read_text()

    assert 'new URL("radar_timeline.js", navigationScriptUrl).href' in navigation
    assert 'if (viewId === "safety") ensureRadarTimeline()' in navigation
    assert 'window.apiWithFallback("/api/radar", "safety-radar")' in radar
    assert 'frame.kind === "radar_observed" || frame.kind === "radar_nowcast"' in radar
    assert 'This does not mean precipitation is absent.' in radar
    assert 'raster_rendering_available === false' in radar
    assert 'const CACHE = "rozkalns-weather-v21"' in worker
    assert '"/static/radar_timeline.js"' in worker


def test_safety_view_lazy_loads_accessible_observed_nowcast_timeline(tmp_path: Path) -> None:
    fixture = tmp_path / "radar-timeline-proof.html"
    fixture.write_text(
        f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>Radar timeline proof</title></head>
<body>
  <a class="skip-link" href="#overview">Skip to weather content</a>
  <main>
    <section id="overview" class="view active"><h1>Overview</h1></section>
    <section id="models" class="view"><h1>Models</h1></section>
    <section id="safety" class="view">
      <h1>Safety</h1>
      <div id="radarState" data-state="loading">LOADING · radar data has not been requested</div>
      <button id="loadRadar" type="button">Load radar metadata</button>
      <pre id="radarOutput"></pre>
    </section>
    <section id="accuracy" class="view"><h1>Accuracy</h1></section>
    <section id="status" class="view"><h1>Status</h1></section>
  </main>
  <nav class="tabs">
    <button data-view="overview" class="active">Overview</button>
    <button data-view="models">Models</button>
    <button data-view="safety">Radar</button>
    <button data-view="accuracy">Accuracy</button>
    <button data-view="status">Status</button>
  </nav>
  <output id="proof"></output>
  <script>
    let radarCalls = 0;
    const radarPayload = {{
      state: 'frames_present',
      frames: [
        {{timestamp:'2026-09-28T11:45:00Z', kind:'radar_observed', source:'RADOLAN observed older', precipitation_5:'must-not-render'}},
        {{timestamp:'2026-09-28T12:30:00Z', kind:'radar_nowcast', source:'RADOLAN nowcast'}},
        {{timestamp:'2026-09-28T11:55:00Z', kind:'radar_observed', source:'RADOLAN observed latest', provider_extra:'must-not-render'}}
      ],
      geometry: {{private:'must-not-render'}},
      map_contract: {{
        rendering_contract: {{
          state:'metadata_only',
          raster_rendering_available:false,
          reason_code:'RADAR_RASTER_CONTRACT_PENDING'
        }}
      }}
    }};

    window.apiWithFallback = async (url, key) => {{
      if (url !== '/api/radar' || key !== 'safety-radar') throw new Error('unexpected radar request');
      radarCalls += 1;
      return {{payload: radarPayload, source:'network', cached_at_utc:'2026-09-28T12:00:00Z', error:null}};
    }};
    window.stateFromResult = () => 'fresh';
    window.formatTimestamp = (value) => value;
    window.setSurfaceState = (id, state, message) => {{
      const element = document.getElementById(id);
      element.dataset.state = state;
      element.textContent = `${{state.toUpperCase()}} · ${{message}}`;
    }};

    document.querySelectorAll('.tabs button[data-view]').forEach((button) => {{
      button.onclick = () => {{
        document.querySelectorAll('.view').forEach((view) => view.classList.toggle('active', view.id === button.dataset.view));
        document.querySelectorAll('.tabs button[data-view]').forEach((item) => item.classList.toggle('active', item === button));
      }};
    }});
  </script>
  <script src="{NAVIGATION.as_uri()}"></script>
  <script>
    const proof = document.getElementById('proof');
    setTimeout(() => {{
      proof.dataset.noInitialFetch = String(radarCalls === 0 && !window.rozkalnsRadarTimeline);
      document.querySelector('[data-view="safety"]').click();
    }}, 30);

    setTimeout(() => {{
      const output = document.getElementById('radarOutput');
      const text = output.textContent;
      proof.dataset.lazyFetch = String(radarCalls === 1 && Boolean(window.rozkalnsRadarTimeline));
      proof.dataset.region = String(output.getAttribute('role') === 'region' && output.getAttribute('aria-label') === 'DWD radar frame timeline');
      proof.dataset.frameCount = String(output.querySelectorAll('ol[aria-label="Available radar frames"] li').length);
      proof.dataset.latestObserved = String(text.includes('Latest observed · 2026-09-28T11:55:00Z · RADOLAN observed latest'));
      proof.dataset.nowcast = String(text.includes('Nowcast · 2026-09-28T12:30:00Z · RADOLAN nowcast'));
      proof.dataset.noRaw = String(!text.includes('precipitation_5') && !text.includes('provider_extra') && !text.includes('geometry') && !text.includes('must-not-render'));
      proof.dataset.pendingImagery = String(text.includes('Radar imagery is not rendered yet') && text.includes('projection'));
      proof.dataset.fresh = String(document.getElementById('radarState').dataset.state === 'fresh');

      window.rozkalnsRadarTimeline.renderTimeline({{
        frames: [],
        map_contract: {{rendering_contract: {{raster_rendering_available:false, reason_code:'RADAR_RASTER_CONTRACT_PENDING'}}}}
      }});
      proof.dataset.emptySafe = String(document.getElementById('radarOutput').textContent.includes('This does not mean precipitation is absent.'));
      document.getElementById('loadRadar').click();
    }}, 240);

    setTimeout(() => {{
      proof.dataset.refresh = String(radarCalls === 2 && document.getElementById('loadRadar').textContent === 'Refresh radar metadata');
      proof.dataset.ready = 'true';
    }}, 420);
  </script>
</body>
</html>
"""
    )

    rendered = _run_browser(fixture.as_uri())
    for attribute in (
        "no-initial-fetch",
        "lazy-fetch",
        "region",
        "latest-observed",
        "nowcast",
        "no-raw",
        "pending-imagery",
        "fresh",
        "empty-safe",
        "refresh",
        "ready",
    ):
        assert f'data-{attribute}="true"' in rendered, rendered
    assert 'data-frame-count="3"' in rendered, rendered
