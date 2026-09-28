from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"
FORECAST_LOADING = STATIC / "forecast_loading.js"
OBSERVATION_AGE = STATIC / "observation_age.js"
SW = STATIC / "sw.js"


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the independent forecast-loading proof")


def _run_browser(uri: str, *, budget_ms: int = 1200) -> str:
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


def test_forecast_loader_is_sibling_module_and_part_of_offline_shell() -> None:
    loader = OBSERVATION_AGE.read_text()
    forecast = FORECAST_LOADING.read_text()
    worker = SW.read_text()

    assert 'new URL("forecast_loading.js", OBSERVATION_SCRIPT_URL).href' in loader
    assert 'script.dataset.rozkalnsForecastLoading = "true"' in loader
    assert 'PUBLIC_DEFAULT_LOCATION = "station_05480"' in forecast
    assert 'selector.value === "home" && providerHealthStillLoading()' in forecast
    assert 'selectedLocation() === locationId' in forecast
    assert '"/static/forecast_loading.js"' in worker
    assert '"/static/request_lifecycle.js"' in worker
    assert 'const CACHE = "rozkalns-weather-v24"' in worker


def _write_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "independent-forecast-loading.html"
    fixture.write_text(
        f"""<!doctype html>
<html><head><meta charset="utf-8"></head><body>
  <select id="forecastLocation">
    <option value="home" selected>Home</option>
    <option value="station_05480">05480</option>
    <option value="station_10416">10416</option>
  </select>
  <div id="providerState" data-state="loading">health pending</div>
  <div id="modelsTempState"></div><div id="overviewTempState"></div>
  <div id="modelsPrecipState"></div><div id="overviewPrecipState"></div>
  <div id="dailyState"></div><div id="dailyGrid"></div><div id="heroHighLow"></div>
  <output id="proof"></output>
  <script>
    const scenario = new URLSearchParams(location.search).get('scenario') || 'independent';
    const calls = [];
    const renders = {{temperature:0, precipitation:0, daily:0, hourly:0}};
    let lastTemperatureLocation = '';
    let lastDailyLocation = '';
    let pendingHealthState = '';
    let pendingHealthMessage = '';

    function result(locationId, variable) {{
      const row = {{provider:'icon_d2', model_name:'ICON-D2', statistic:'deterministic', value:12, valid_time_utc:'2026-09-28T18:00:00Z', retrieved_at_utc:'2026-09-28T16:00:00Z'}};
      if (variable === 'daily') return {{payload:{{location:{{id:locationId}},days_by_provider:[{{provider:'icon_d2',date:'2026-09-28',temperature_min_c:8,temperature_max_c:14}}]}},source:'network',cached_at_utc:'2026-09-28T16:00:00Z',error:null}};
      return {{payload:{{location:{{id:locationId}},series:[row]}},source:'network',cached_at_utc:'2026-09-28T16:00:00Z',error:null}};
    }}

    window.stateFromResult = () => 'fresh';
    window.formatTimestamp = (value) => value;
    window.providerSurfaceState = (_rows, healthMap) => ({{state:Object.keys(healthMap || {{}}).length ? 'fresh' : 'stale',message:'base health-dependent state'}});
    window.setSurfaceState = (id, state, message) => {{
      const element = document.getElementById(id);
      if (element) {{ element.dataset.state = state; element.textContent = message; }}
    }};
    window.renderTemperature = (value, healthMap) => {{
      renders.temperature += 1;
      lastTemperatureLocation = value.payload.location.id;
      const state = window.providerSurfaceState(value.payload.series, healthMap, value);
      pendingHealthState = state.state;
      pendingHealthMessage = state.message;
    }};
    window.renderModelSnapshot = () => {{}};
    window.renderPrecipitation = () => {{ renders.precipitation += 1; }};
    window.renderConsumerHourly = () => {{ renders.hourly += 1; }};
    window.renderDaily = (value) => {{ renders.daily += 1; lastDailyLocation = value.payload.location.id; }};

    window.apiWithFallback = (url, _key, _options = {{}}) => {{
      calls.push(String(url));
      const parsed = new URL(String(url), 'https://weather.invalid');
      const locationId = parsed.searchParams.get('location_id');
      if (parsed.pathname === '/api/daily') {{
        const delay = scenario === 'independent' ? 35 : 20;
        return new Promise((resolve) => setTimeout(() => resolve(result(locationId, 'daily')), delay));
      }}
      const variable = parsed.searchParams.get('variable');
      if (scenario === 'independent' && variable === 'temperature_2m') return new Promise(() => {{}});
      if (scenario === 'race' && variable === 'temperature_2m' && locationId === 'station_05480') {{
        return new Promise((resolve) => setTimeout(() => resolve(result(locationId, variable)), 320));
      }}
      const delay = scenario === 'race' && locationId === 'station_10416' ? 25 : 20;
      return new Promise((resolve) => setTimeout(() => resolve(result(locationId, variable)), delay));
    }};
    window.RozkalnsRequestLifecycle = {{apiWithTimeoutFallback: window.apiWithFallback}};
  </script>
  <script src="{FORECAST_LOADING.as_uri()}"></script>
  <script>
    const proof = document.getElementById('proof');
    if (scenario === 'race') {{
      setTimeout(() => {{
        const selector = document.getElementById('forecastLocation');
        selector.value = 'station_10416';
        selector.dispatchEvent(new Event('change', {{bubbles:true}}));
      }}, 60);
    }}
    setTimeout(() => {{
      proof.dataset.scenario = scenario;
      proof.dataset.location = document.getElementById('forecastLocation').value;
      proof.dataset.calls = String(calls.length);
      proof.dataset.temperatureRenders = String(renders.temperature);
      proof.dataset.precipitationRenders = String(renders.precipitation);
      proof.dataset.dailyRenders = String(renders.daily);
      proof.dataset.hourlyRenders = String(renders.hourly);
      proof.dataset.lastTemperatureLocation = lastTemperatureLocation;
      proof.dataset.lastDailyLocation = lastDailyLocation;
      proof.dataset.pendingHealthState = pendingHealthState;
      proof.dataset.pendingHealthMessage = pendingHealthMessage;
      proof.dataset.ready = 'true';
    }}, scenario === 'race' ? 520 : 180);
  </script>
</body></html>"""
    )
    return fixture


def test_daily_and_hourly_surfaces_do_not_wait_for_each_other_or_health(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path)
    rendered = _run_browser(f"{fixture.as_uri()}?scenario=independent")

    assert 'data-ready="true"' in rendered, rendered
    assert 'data-location="station_05480"' in rendered, rendered
    assert 'data-temperature-renders="0"' in rendered, rendered
    assert 'data-precipitation-renders="1"' in rendered, rendered
    assert 'data-daily-renders="1"' in rendered, rendered
    assert 'data-hourly-renders="0"' in rendered, rendered
    assert 'data-last-daily-location="station_05480"' in rendered, rendered


def test_location_change_ignores_late_response_from_previous_location(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path)
    rendered = _run_browser(f"{fixture.as_uri()}?scenario=race", budget_ms=1400)

    assert 'data-ready="true"' in rendered, rendered
    assert 'data-location="station_10416"' in rendered, rendered
    assert 'data-temperature-renders="1"' in rendered, rendered
    assert 'data-last-temperature-location="station_10416"' in rendered, rendered
    assert 'data-last-daily-location="station_10416"' in rendered, rendered
    assert 'data-pending-health-state="fresh"' in rendered, rendered
    assert 'provider health is still pending' in rendered, rendered
