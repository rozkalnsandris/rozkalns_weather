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
    raise AssertionError("A Chromium-family browser is required for the observation-age regression proof")


def test_observation_age_advances_and_turns_stale_without_refetch(tmp_path: Path) -> None:
    fixture = tmp_path / "observation-age.html"
    fixture.write_text(
        f"""<!doctype html>
<html><head><meta charset=\"utf-8\"></head><body>
  <div id=\"heroUpdated\"></div>
  <div id=\"currentState\" class=\"surface-state state-fresh\" data-state=\"fresh\" role=\"status\"></div>
  <output id=\"proof\"></output>
  <script>
    window.fetchCalls = 0;
    window.fetch = () => {{ window.fetchCalls += 1; return Promise.reject(new Error('unexpected fetch')); }};
    window.setSurfaceState = (id, state, message) => {{
      const element = document.getElementById(id);
      element.hidden = false;
      element.removeAttribute('aria-hidden');
      element.className = `surface-state state-${{state}}`;
      element.dataset.state = state;
      element.textContent = `${{state.toUpperCase()}} · ${{message}}`;
    }};
    window.renderCurrent = () => {{
      const state = document.getElementById('currentState');
      state.className = 'surface-state state-fresh';
      state.dataset.state = 'fresh';
      state.textContent = 'FRESH · DWD observation current';
    }};
  </script>
  <script src=\"{OBSERVATION_AGE_JS.as_uri()}\"></script>
  <script>
    const observedMs = Date.now() - 10 * 60 * 1000;
    const observed = new Date(observedMs).toISOString();
    const result = {{ payload: {{ observations: [{{ observed_at_utc: observed }}] }} }};
    window.renderCurrent(result, {{}});

    window.RozkalnsObservationAge.updateObservationAge(result, observedMs + 45 * 60 * 1000);
    const freshText = document.getElementById('heroUpdated').textContent;
    const freshState = document.getElementById('currentState').dataset.state;

    window.RozkalnsObservationAge.updateObservationAge(result, observedMs + 181 * 60 * 1000);
    const state = document.getElementById('currentState');
    const proof = document.getElementById('proof');
    proof.dataset.ready = 'true';
    proof.dataset.freshText = freshText;
    proof.dataset.freshState = freshState;
    proof.dataset.staleState = state.dataset.state;
    proof.dataset.staleManaged = state.dataset.observationAgeManagedStale || '';
    proof.dataset.staleText = document.getElementById('heroUpdated').textContent;
    proof.dataset.fetchCalls = String(window.fetchCalls);
    proof.dataset.threshold = String(window.RozkalnsObservationAge.OBSERVATION_FRESH_MINUTES);
  </script>
</body></html>"""
    )

    completed = subprocess.run(
        [
            _browser_binary(),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            "--virtual-time-budget=800",
            "--dump-dom",
            fixture.as_uri(),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    rendered = completed.stdout

    assert 'data-ready="true"' in rendered, rendered
    assert 'data-fresh-state="fresh"' in rendered, rendered
    assert 'data-fresh-text=' in rendered and '45 min ago' in rendered, rendered
    assert 'data-stale-state="stale"' in rendered, rendered
    assert 'data-stale-managed="true"' in rendered, rendered
    assert '3 h 1 min old' in rendered, rendered
    assert 'data-fetch-calls="0"' in rendered, rendered
    assert 'data-threshold="180"' in rendered, rendered
