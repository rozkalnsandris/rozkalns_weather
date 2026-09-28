from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"
REQUEST_LIFECYCLE = STATIC / "request_lifecycle.js"
FORECAST_LOADING = STATIC / "forecast_loading.js"


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the request lifecycle proof")


def _run_browser(uri: str, *, budget_ms: int = 900) -> str:
    completed = subprocess.run(
        [
            _browser_binary(),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            "--window-size=900,700",
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


def test_request_lifecycle_times_out_aborts_and_preserves_stale_cache(tmp_path: Path) -> None:
    fixture = tmp_path / "request-lifecycle.html"
    fixture.write_text(
        f"""<!doctype html><html><body><output id="proof"></output>
<script>
  let aborts = 0;
  localStorage.setItem('rozkalns-weather:pwa-cache:v1:cached-key', JSON.stringify({{
    cached_at_utc: '2026-09-28T16:00:00Z',
    payload: {{marker: 'cached-value'}}
  }}));
  window.fetch = (_url, options = {{}}) => new Promise((_resolve, reject) => {{
    const signal = options.signal;
    const onAbort = () => {{
      aborts += 1;
      reject(new DOMException('Aborted', 'AbortError'));
    }};
    if (signal?.aborted) onAbort();
    else signal?.addEventListener('abort', onAbort, {{once: true}});
  }});
</script>
<script src="{REQUEST_LIFECYCLE.as_uri()}"></script>
<script>
(async () => {{
  const proof = document.getElementById('proof');
  const api = window.RozkalnsRequestLifecycle.apiWithTimeoutFallback;
  let timeoutError = '';
  try {{
    await api('/timeout', 'no-cache', {{timeoutMs: 30}});
  }} catch (error) {{
    timeoutError = String(error);
  }}

  const cached = await api('/cached', 'cached-key', {{timeoutMs: 30}});

  const controller = new AbortController();
  const externalPromise = api('/external', 'no-external-cache', {{
    signal: controller.signal,
    timeoutMs: 250,
  }}).then(() => null, (error) => error);
  setTimeout(() => controller.abort(), 10);
  const externalError = await externalPromise;

  proof.dataset.timeout = timeoutError;
  proof.dataset.cachedSource = cached.source;
  proof.dataset.cachedMarker = cached.payload.marker;
  proof.dataset.cachedError = cached.error;
  proof.dataset.externalName = externalError?.name || '';
  proof.dataset.aborts = String(aborts);
  proof.dataset.ready = 'true';
}})();
</script></body></html>"""
    )

    rendered = _run_browser(fixture.as_uri())
    assert 'data-ready="true"' in rendered, rendered
    assert 'Request timed out after 30 ms' in rendered, rendered
    assert 'data-cached-source="stale-cache"' in rendered, rendered
    assert 'data-cached-marker="cached-value"' in rendered, rendered
    assert 'data-external-name="AbortError"' in rendered, rendered
    assert 'data-aborts="3"' in rendered, rendered


def test_forecast_location_change_aborts_superseded_request_group(tmp_path: Path) -> None:
    fixture = tmp_path / "forecast-abort.html"
    fixture.write_text(
        f"""<!doctype html><html><body>
<select id="forecastLocation"><option value="home" selected>Home</option><option value="station_05480">05480</option><option value="station_10416">10416</option></select>
<div id="providerState" data-state="loading"></div>
<div id="modelsTempState"></div><div id="overviewTempState"></div><div id="modelsPrecipState"></div><div id="overviewPrecipState"></div><div id="dailyState"></div><div id="dailyGrid"></div><div id="heroHighLow"></div>
<output id="proof"></output>
<script>
  let aborts = 0;
  const renderedLocations = [];
  function response(locationId, kind) {{
    if (kind === 'daily') return {{payload: {{location: {{id: locationId}}, days_by_provider: [{{provider:'icon_d2', date:'2026-09-28', temperature_min_c:8, temperature_max_c:14}}]}}, source:'network', cached_at_utc:'2026-09-28T16:00:00Z'}};
    return {{payload: {{location: {{id: locationId}}, series: [{{provider:'icon_d2', statistic:'deterministic', value:12, valid_time_utc:'2026-09-28T18:00:00Z'}}]}}, source:'network', cached_at_utc:'2026-09-28T16:00:00Z'}};
  }}
  window.apiWithFallback = (url, _key, options = {{}}) => new Promise((resolve, reject) => {{
    const parsed = new URL(url, 'https://weather.invalid');
    const locationId = parsed.searchParams.get('location_id');
    const kind = parsed.pathname === '/api/daily' ? 'daily' : parsed.searchParams.get('variable');
    const delay = locationId === 'station_05480' ? 320 : 25;
    const timer = setTimeout(() => resolve(response(locationId, kind)), delay);
    const signal = options.signal;
    signal?.addEventListener('abort', () => {{
      aborts += 1;
      clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    }}, {{once: true}});
  }});
  window.RozkalnsRequestLifecycle = {{apiWithTimeoutFallback: window.apiWithFallback}};
  window.stateFromResult = () => 'fresh';
  window.formatTimestamp = (value) => value;
  window.providerSurfaceState = () => ({{state:'fresh', message:'ok'}});
  window.setSurfaceState = () => {{}};
  window.renderTemperature = (result) => renderedLocations.push('temp:' + result.payload.location.id);
  window.renderModelSnapshot = () => {{}};
  window.renderPrecipitation = (result) => renderedLocations.push('precip:' + result.payload.location.id);
  window.renderConsumerHourly = () => {{}};
  window.renderDaily = (result) => renderedLocations.push('daily:' + result.payload.location.id);
</script>
<script src="{FORECAST_LOADING.as_uri()}"></script>
<script>
  setTimeout(() => {{
    const selector = document.getElementById('forecastLocation');
    selector.value = 'station_10416';
    selector.dispatchEvent(new Event('change', {{bubbles:true}}));
  }}, 55);
  setTimeout(() => {{
    const proof = document.getElementById('proof');
    proof.dataset.aborts = String(aborts);
    proof.dataset.location = document.getElementById('forecastLocation').value;
    proof.dataset.renders = renderedLocations.join(',');
    proof.dataset.ready = 'true';
  }}, 430);
</script>
</body></html>"""
    )

    rendered = _run_browser(fixture.as_uri(), budget_ms=1100)
    assert 'data-ready="true"' in rendered, rendered
    assert 'data-aborts="3"' in rendered, rendered
    assert 'data-location="station_10416"' in rendered, rendered
    assert 'temp:station_10416' in rendered, rendered
    assert 'precip:station_10416' in rendered, rendered
    assert 'daily:station_10416' in rendered, rendered
    assert 'station_05480' not in rendered.split('data-renders="', 1)[1].split('"', 1)[0], rendered
