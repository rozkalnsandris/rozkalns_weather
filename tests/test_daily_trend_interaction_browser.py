from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DAILY_TREND_JS = ROOT / "src" / "rozkalns_weather" / "static" / "daily_trend.js"


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the daily interaction regression proof")


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


def _write_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "daily-trend-interaction-proof.html"
    rows = """[
      {date:'2026-10-01',provider:'icon_d2',model_name:'ICON-D2',temperature_min_c:8,temperature_max_c:16,precipitation_total_mm:0,init_time_utc:'2026-09-30T18:00:00Z',retrieved_at_utc:'2026-09-30T19:00:00Z'},
      {date:'2026-10-02',provider:'icon_d2',model_name:'ICON-D2',temperature_min_c:9,temperature_max_c:17,precipitation_total_mm:0.4,init_time_utc:'2026-09-30T18:00:00Z',retrieved_at_utc:'2026-09-30T19:00:00Z'},
      {date:'2026-10-03',provider:'icon_d2',model_name:'ICON-D2',temperature_min_c:7,temperature_max_c:15,precipitation_total_mm:0,init_time_utc:'2026-09-30T18:00:00Z',retrieved_at_utc:'2026-09-30T19:00:00Z'},
      {date:'2026-10-04',provider:'icon_d2',model_name:'ICON-D2',temperature_min_c:6,temperature_max_c:14,precipitation_total_mm:2.3,init_time_utc:'2026-09-30T18:00:00Z',retrieved_at_utc:'2026-09-30T19:00:00Z'},
      {date:'2026-10-05',provider:'icon_d2',model_name:'ICON-D2',temperature_min_c:8,temperature_max_c:17,precipitation_total_mm:0,init_time_utc:'2026-09-30T18:00:00Z',retrieved_at_utc:'2026-09-30T19:00:00Z'},
      {date:'2026-10-06',provider:'icon_d2',model_name:'ICON-D2',temperature_min_c:10,temperature_max_c:19,precipitation_total_mm:0.1,init_time_utc:'2026-09-30T18:00:00Z',retrieved_at_utc:'2026-09-30T19:00:00Z'},
      {date:'2026-10-07',provider:'icon_d2',model_name:'ICON-D2',temperature_min_c:9,temperature_max_c:18,precipitation_total_mm:0,init_time_utc:'2026-09-30T18:00:00Z',retrieved_at_utc:'2026-09-30T19:00:00Z'},
      {date:'2026-10-08',provider:'icon_d2',model_name:'ICON-D2',temperature_min_c:null,temperature_max_c:18,precipitation_total_mm:1.2,init_time_utc:'2026-09-30T18:00:00Z',retrieved_at_utc:'2026-09-30T19:00:00Z'},
      {date:'2026-10-09',provider:'icon_d2',model_name:'ICON-D2',temperature_min_c:7,temperature_max_c:15,precipitation_total_mm:null,init_time_utc:'2026-09-30T18:00:00Z',retrieved_at_utc:'2026-09-30T19:00:00Z'},
      {date:'2026-10-10',provider:'icon_d2',model_name:'ICON-D2',temperature_min_c:6,temperature_max_c:14,precipitation_total_mm:0,init_time_utc:'2026-09-30T18:00:00Z',retrieved_at_utc:'2026-09-30T19:00:00Z'}
    ]"""
    fixture.write_text(
        f"""<!doctype html>
<html><body>
  <div id="target"></div>
  <output id="proof"></output>
  <script src="{DAILY_TREND_JS.as_uri()}"></script>
  <script>
    const rows = {rows};
    const target = document.getElementById('target');
    const proof = document.getElementById('proof');
    window.RozkalnsDailyTrend.render(target, rows, 'icon_d2');

    const initialCards = [...target.querySelectorAll('[data-date]')];
    const horizon14 = target.querySelector('[data-days="14"]');
    const horizonAvailable = horizon14 && !horizon14.disabled;
    horizon14.click();
    const expandedCards = [...target.querySelectorAll('[data-date]')];

    target.querySelector('[data-date="2026-10-08"]').click();
    const selected = target.querySelector('.trend-selected');
    const selectedButton = target.querySelector('[data-date="2026-10-08"]');
    const sourceText = target.querySelector('.trend-table').textContent;

    proof.dataset.initialCount = String(initialCards.length);
    proof.dataset.expandedCount = String(expandedCards.length);
    proof.dataset.horizonAvailable = String(horizonAvailable);
    proof.dataset.semanticButtons = String(expandedCards.every((node) => node.tagName === 'BUTTON'));
    proof.dataset.selectedPressed = selectedButton.getAttribute('aria-pressed');
    proof.dataset.focusDate = document.activeElement?.dataset?.date || '';
    proof.dataset.provider = target.dataset.provider || '';
    proof.dataset.missingPreserved = String(selected.textContent.includes('Min —'));
    proof.dataset.missingNotZero = String(!selected.textContent.includes('Min 0°'));
    proof.dataset.rainAmount = String(selected.textContent.includes('Rain 1.2 mm'));
    proof.dataset.sourcePreserved = String(sourceText.includes('icon_d2') && sourceText.includes('API daily aggregates'));
    proof.dataset.ready = 'true';
  </script>
</body></html>"""
    )
    return fixture


def test_daily_horizon_selection_and_missing_values_run_in_real_browser(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path)
    rendered = _run_browser(fixture.as_uri())

    assert 'data-ready="true"' in rendered, rendered
    assert 'data-initial-count="7"' in rendered, rendered
    assert 'data-expanded-count="10"' in rendered, rendered
    assert 'data-horizon-available="true"' in rendered, rendered
    assert 'data-semantic-buttons="true"' in rendered, rendered
    assert 'data-selected-pressed="true"' in rendered, rendered
    assert 'data-focus-date="2026-10-08"' in rendered, rendered
    assert 'data-provider="icon_d2"' in rendered, rendered
    assert 'data-missing-preserved="true"' in rendered, rendered
    assert 'data-missing-not-zero="true"' in rendered, rendered
    assert 'data-rain-amount="true"' in rendered, rendered
    assert 'data-source-preserved="true"' in rendered, rendered
