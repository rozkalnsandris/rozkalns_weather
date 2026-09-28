from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
CONSUMER_UI_JS = ROOT / "src" / "rozkalns_weather" / "static" / "consumer_ui.js"


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the hourly interaction regression proof")


def _run_browser(uri: str, *, budget_ms: int = 1200) -> str:
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


def _write_fixture(tmp_path: Path, *, wind_failure: bool) -> Path:
    fixture = tmp_path / ("hourly-wind-failure.html" if wind_failure else "hourly-details.html")
    api_stub = """
      window.apiWithFallback = (url) => {
        window.windUrl = url;
        return Promise.reject(new Error('wind unavailable'));
      };
    """ if wind_failure else """
      window.apiWithFallback = (url) => {
        window.windUrl = url;
        return Promise.resolve({
          source: 'network',
          payload: {
            series: [
              {
                provider: 'icon_d2', model_name: 'ICON-D2', model_version: '2026-09',
                init_time_utc: '2026-10-01T00:00:00Z', retrieved_at_utc: '2026-10-01T01:00:00Z',
                valid_time_utc: '2026-10-01T13:00:00Z', lead_hours: 13,
                variable: 'wind_speed_10m', statistic: 'deterministic', value: 5.0, unit: 'm/s'
              }
            ]
          }
        });
      };
    """
    fixture.write_text(
        f"""<!doctype html>
<html><head><meta charset=\"utf-8\"></head><body>
  <div id=\"hourlyStrip\"></div>
  <output id=\"proof\"></output>
  <script>
    window.chooseProvider = () => 'icon_d2';
    window.canonicalProviderRows = (rows, provider) => rows.filter((row) => row.provider === provider).slice().sort((a, b) => a.valid_time_utc.localeCompare(b.valid_time_utc));
    window.futureRows = (rows, count) => rows.slice(0, count);
    window.formatLocalTime = (value) => new Intl.DateTimeFormat('en-GB', {{ timeZone: 'Europe/Berlin', hour: '2-digit', minute: '2-digit' }}).format(new Date(value));
    {api_stub}

    window.renderConsumerHourly = (tempResult, precipResult) => {{
      const rows = tempResult.payload.series;
      const precip = new Map(precipResult.payload.series.map((row) => [row.valid_time_utc, row.value]));
      document.getElementById('hourlyStrip').innerHTML = rows.map((row) => `
        <div class=\"hour-card\">
          <div class=\"hour-label\">${{window.formatLocalTime(row.valid_time_utc)}}</div>
          <div class=\"hour-icon\">·</div>
          <strong>${{Math.round(row.value)}}°</strong>
          <small>${{precip.has(row.valid_time_utc) ? Number(precip.get(row.valid_time_utc)).toFixed(1) + ' mm' : '— mm'}}</small>
        </div>`).join('');
    }};
  </script>
  <script src=\"{CONSUMER_UI_JS.as_uri()}\"></script>
  <script>
    const tempResult = {{
      payload: {{
        location: {{ id: 'station_05480' }},
        series: [
          {{
            provider: 'icon_d2', model_name: 'ICON-D2', model_version: '2026-09',
            init_time_utc: '2026-10-01T00:00:00Z', retrieved_at_utc: '2026-10-01T01:00:00Z',
            valid_time_utc: '2026-10-01T12:00:00Z', lead_hours: 12,
            variable: 'temperature_2m', statistic: 'deterministic', value: 11, unit: 'degC'
          }},
          {{
            provider: 'icon_d2', model_name: 'ICON-D2', model_version: '2026-09',
            init_time_utc: '2026-10-01T00:00:00Z', retrieved_at_utc: '2026-10-01T01:00:00Z',
            valid_time_utc: '2026-10-01T13:00:00Z', lead_hours: 13,
            variable: 'temperature_2m', statistic: 'deterministic', value: 12, unit: 'degC'
          }}
        ]
      }}
    }};
    const precipResult = {{
      payload: {{
        location: {{ id: 'station_05480' }},
        series: [
          {{
            provider: 'icon_d2', model_name: 'ICON-D2', model_version: '2026-09',
            init_time_utc: '2026-10-01T00:00:00Z', retrieved_at_utc: '2026-10-01T01:00:00Z',
            valid_time_utc: '2026-10-01T12:00:00Z', lead_hours: 12,
            variable: 'precipitation_1h', statistic: 'deterministic', value: 0.6, unit: 'mm'
          }}
        ]
      }}
    }};

    window.renderConsumerHourly(tempResult, precipResult, {{}});
    setTimeout(() => {{
      const cards = [...document.querySelectorAll('#hourlyStrip .hour-card')];
      const second = cards[1];
      second.focus();
      second.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true }}));
      const target = document.getElementById('hourlyDetail');
      const metrics = [...target.querySelectorAll('.hourly-detail-metric')];
      const metric = (name) => metrics.find((node) => node.querySelector('small')?.textContent === name);
      const proof = document.getElementById('proof');
      proof.dataset.ready = 'true';
      proof.dataset.cardCount = String(cards.length);
      proof.dataset.roleButton = String(second.getAttribute('role') === 'button');
      proof.dataset.tabindex = second.getAttribute('tabindex') || '';
      proof.dataset.controls = second.getAttribute('aria-controls') || '';
      proof.dataset.selected = second.getAttribute('aria-pressed') || '';
      proof.dataset.focused = String(document.activeElement === second);
      proof.dataset.temperature = metric('Temperature')?.querySelector('strong')?.textContent || '';
      proof.dataset.precipitation = metric('Precipitation')?.querySelector('strong')?.textContent || '';
      proof.dataset.precipitationNote = metric('Precipitation')?.querySelector('span')?.textContent || '';
      proof.dataset.wind = metric('Wind')?.querySelector('strong')?.textContent || '';
      proof.dataset.windNote = metric('Wind')?.querySelector('span')?.textContent || '';
      proof.dataset.provider = String(target.textContent.includes('ICON-D2'));
      proof.dataset.valid = String(target.textContent.includes('2026-10-01T13:00:00Z'));
      proof.dataset.init = String(target.textContent.includes('2026-10-01T00:00:00Z'));
      proof.dataset.lead = String(target.textContent.includes('lead 13 h'));
      proof.dataset.windUrl = window.windUrl || '';
    }}, 80);
  </script>
</body></html>"""
    )
    return fixture


def test_hourly_cards_are_keyboard_selectable_with_exact_provenance_and_wind(tmp_path: Path) -> None:
    rendered = _run_browser(_write_fixture(tmp_path, wind_failure=False).as_uri())

    assert 'data-ready="true"' in rendered, rendered
    assert 'data-card-count="2"' in rendered, rendered
    assert 'data-role-button="true"' in rendered, rendered
    assert 'data-tabindex="0"' in rendered, rendered
    assert 'data-controls="hourlyDetail"' in rendered, rendered
    assert 'data-selected="true"' in rendered, rendered
    assert 'data-focused="true"' in rendered, rendered
    assert 'data-temperature="12 °C"' in rendered, rendered
    assert 'data-precipitation="—"' in rendered, rendered
    assert 'data-precipitation-note="same-run value unavailable"' in rendered, rendered
    assert 'data-wind="18 km/h"' in rendered, rendered
    assert 'data-wind-note="5.0 m/s source"' in rendered, rendered
    assert 'data-provider="true"' in rendered, rendered
    assert 'data-valid="true"' in rendered, rendered
    assert 'data-init="true"' in rendered, rendered
    assert 'data-lead="true"' in rendered, rendered
    assert 'variable=wind_speed_10m' in rendered, rendered
    assert 'location_id=station_05480' in rendered, rendered


def test_wind_failure_does_not_remove_other_hourly_details(tmp_path: Path) -> None:
    rendered = _run_browser(_write_fixture(tmp_path, wind_failure=True).as_uri())

    assert 'data-ready="true"' in rendered, rendered
    assert 'data-card-count="2"' in rendered, rendered
    assert 'data-temperature="12 °C"' in rendered, rendered
    assert 'data-precipitation="—"' in rendered, rendered
    assert 'data-wind="—"' in rendered, rendered
    assert 'data-wind-note="wind data unavailable"' in rendered, rendered
    assert 'data-provider="true"' in rendered, rendered
    assert 'data-valid="true"' in rendered, rendered
