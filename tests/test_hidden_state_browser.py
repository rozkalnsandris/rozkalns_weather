from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"
INDEX = STATIC / "index.html"
CONSUMER_UI = STATIC / "consumer_ui.js"


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the hidden-state regression proof")


def _run_browser(uri: str, *, width: int = 900, height: int = 700, budget_ms: int = 1200) -> str:
    completed = subprocess.run(
        [
            _browser_binary(),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            f"--window-size={width},{height}",
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


def test_fresh_hero_state_is_render_hidden_and_degraded_state_restores(tmp_path: Path) -> None:
    index = INDEX.read_text()
    match = re.search(
        r'<style id="overview-hero-state-contract">\s*(.*?)\s*</style>',
        index,
        re.DOTALL,
    )
    assert match, "Overview hero hidden-state CSS contract must remain in the real shell"
    contract = match.group(1)

    fixture = tmp_path / "hero-hidden-state-proof.html"
    fixture.write_text(
        f"""<!doctype html>
<html>
<head>
  <style id="overview-hero-state-contract">
{contract}
  </style>
</head>
<body>
  <div id="heroUpdated"></div>
  <div id="heroFeels"></div>
  <div id="heroIcon"></div>
  <div id="currentState" class="surface-state state-loading hero-state" role="status" aria-live="polite" aria-atomic="true">LOADING</div>
  <script>
    window.setSurfaceState = function(id, state, message) {{
      const element = document.getElementById(id);
      element.dataset.state = state;
      element.setAttribute('role', 'status');
      element.setAttribute('aria-live', 'polite');
      element.setAttribute('aria-atomic', 'true');
      element.textContent = `${{state.toUpperCase()}} · ${{message}}`;
    }};
    window.renderCurrent = function() {{
      document.getElementById('currentState').dataset.state = 'fresh';
    }};
  </script>
  <script src="{CONSUMER_UI.as_uri()}"></script>
  <script>
    const state = document.getElementById('currentState');
    window.renderCurrent({{
      payload: {{ observations: [{{ observed_at_utc: new Date().toISOString() }}] }}
    }}, {{}});

    document.body.dataset.freshHidden = String(state.hidden);
    document.body.dataset.freshDisplay = getComputedStyle(state).display;
    document.body.dataset.freshAriaHidden = String(state.getAttribute('aria-hidden') === 'true');
    document.body.dataset.freshRoleRemoved = String(!state.hasAttribute('role'));

    window.setSurfaceState('currentState', 'stale', 'DWD observation is not current');
    document.body.dataset.staleHidden = String(state.hidden);
    document.body.dataset.staleDisplay = getComputedStyle(state).display;
    document.body.dataset.staleAriaHiddenRemoved = String(!state.hasAttribute('aria-hidden'));
    document.body.dataset.staleRole = state.getAttribute('role') || '';
    document.body.dataset.ready = 'true';
  </script>
</body>
</html>
"""
    )

    rendered = _run_browser(fixture.as_uri())
    assert 'data-ready="true"' in rendered, rendered
    assert 'data-fresh-hidden="true"' in rendered, rendered
    assert 'data-fresh-display="none"' in rendered, rendered
    assert 'data-fresh-aria-hidden="true"' in rendered, rendered
    assert 'data-fresh-role-removed="true"' in rendered, rendered
    assert 'data-stale-hidden="false"' in rendered, rendered
    assert 'data-stale-display="block"' in rendered, rendered
    assert 'data-stale-aria-hidden-removed="true"' in rendered, rendered
    assert 'data-stale-role="status"' in rendered, rendered
