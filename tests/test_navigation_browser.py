from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"
INDEX = STATIC / "index.html"
APP_CSS = STATIC / "app.css"
ACCEPTED_UI_CSS = STATIC / "accepted_ui.css"
NAVIGATION = STATIC / "navigation_v1.js"
SW = STATIC / "sw.js"


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the navigation regression proof")


def _run_browser(uri: str, *, width: int, height: int = 900, budget_ms: int = 1500) -> str:
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


def test_navigation_source_and_pwa_contract() -> None:
    index = INDEX.read_text()
    navigation = NAVIGATION.read_text()
    sw = SW.read_text()

    assert '<a class="skip-link" href="#overview">Skip to weather content</a>' in index
    assert 'id="overviewWarningsButton" class="warning-open" type="button" data-open-view="safety"' in index
    assert '<button data-view="overview" class="active" aria-current="page">' in index
    assert index.index('/static/app.js') < index.index('/static/navigation_v1.js')
    assert 'window.addEventListener("hashchange"' in navigation
    assert 'setAttribute("aria-current", "page")' in navigation
    assert 'target.focus({ preventScroll: true })' in navigation
    assert 'const CACHE = "rozkalns-weather-v20"' in sw
    assert '"/static/navigation_v1.js"' in sw
    assert '"/static/radar_timeline.js"' in sw
    assert '"/static/status_v1.js"' in sw


def test_hash_navigation_direct_link_focus_and_back_forward(tmp_path: Path) -> None:
    fixture = tmp_path / "navigation-proof.html"
    fixture.write_text(
        f"""<!doctype html>
<html>
<body>
  <a class="skip-link" href="#overview">Skip to weather content</a>
  <main>
    <section id="overview" class="view active"><h1 id="overviewHeading">Overview</h1></section>
    <section id="models" class="view"><h1 id="modelsHeading">Models</h1></section>
    <section id="safety" class="view"><h1 id="safetyHeading">Safety</h1></section>
    <section id="accuracy" class="view"><h1 id="accuracyHeading">Accuracy</h1></section>
    <section id="status" class="view"><h1 id="statusHeading">Status</h1></section>
  </main>
  <nav class="tabs">
    <button data-view="overview" class="active">Overview</button>
    <button data-view="models">Models</button>
    <button data-view="safety">Safety</button>
    <button data-view="accuracy">Accuracy</button>
    <button data-view="status">Status</button>
  </nav>
  <script>
    document.querySelectorAll('.tabs button[data-view]').forEach((button) => {{
      button.onclick = () => {{
        document.querySelectorAll('.view').forEach((view) => view.classList.toggle('active', view.id === button.dataset.view));
        document.querySelectorAll('.tabs button[data-view]').forEach((item) => item.classList.toggle('active', item === button));
      }};
    }});
  </script>
  <script src="{NAVIGATION.as_uri()}"></script>
  <output id="proof"></output>
  <script>
    const proof = document.getElementById('proof');
    let sawStatus = false;

    function active(view) {{
      return document.getElementById(view).classList.contains('active');
    }}
    function current(view) {{
      return document.querySelector(`[data-view="${{view}}"]`).getAttribute('aria-current') === 'page';
    }}

    window.addEventListener('hashchange', () => {{
      if (location.hash === '#status' && !sawStatus) {{
        sawStatus = true;
        proof.dataset.status = String(active('status') && current('status') && document.activeElement.id === 'statusHeading');
        setTimeout(() => history.back(), 20);
        return;
      }}
      if (location.hash === '#models' && sawStatus) {{
        setTimeout(() => {{
          proof.dataset.back = String(active('models') && current('models') && document.activeElement.id === 'modelsHeading');
          proof.dataset.ready = 'true';
        }}, 20);
      }}
    }});

    setTimeout(() => {{
      proof.dataset.direct = String(location.hash === '#models' && active('models') && current('models'));
      document.querySelector('[data-view="status"]').click();
    }}, 20);
  </script>
</body>
</html>
"""
    )

    rendered = _run_browser(fixture.as_uri() + "#models", width=900)
    assert 'data-ready="true"' in rendered, rendered
    assert 'data-direct="true"' in rendered, rendered
    assert 'data-status="true"' in rendered, rendered
    assert 'data-back="true"' in rendered, rendered


def _write_real_shell_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "responsive-shell.html"
    html = INDEX.read_text()
    html = html.replace('href="/static/app.css"', f'href="{APP_CSS.as_uri()}"')
    html = html.replace('href="/static/accepted_ui.css"', f'href="{ACCEPTED_UI_CSS.as_uri()}"')
    html = re.sub(r'\s*<script[^>]+src="/static/[^"]+"[^>]*></script>', "", html)
    proof = f"""
  <script src="{NAVIGATION.as_uri()}"></script>
  <script>
    setTimeout(() => {{
      const root = document.documentElement;
      const navButtons = [...document.querySelectorAll('.bottom-nav [data-view]')];
      const withinViewport = navButtons.every((button) => {{
        const rect = button.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 && rect.left >= -1 && rect.right <= window.innerWidth + 1;
      }});
      const statusButton = document.querySelector('.bottom-nav [data-view="status"]');
      statusButton.focus();
      const statusFocusable = document.activeElement === statusButton;
      statusButton.click();
      setTimeout(() => {{
        window.parent.postMessage({{
          type: 'responsive-proof',
          clientWidth: root.clientWidth,
          noPageOverflow: root.scrollWidth <= root.clientWidth + 1,
          navCount: navButtons.length,
          navWithinViewport: withinViewport,
          statusFocusable,
          statusActive: document.getElementById('status').classList.contains('active'),
          statusCurrent: statusButton.getAttribute('aria-current') === 'page'
        }}, '*');
      }}, 20);
    }}, 50);
  </script>
"""
    html = html.replace("</body>", proof + "\n</body>")
    fixture.write_text(html)
    return fixture


def _write_viewport_harness(tmp_path: Path, fixture: Path, width: int) -> Path:
    harness = tmp_path / f"responsive-harness-{width}.html"
    harness.write_text(
        f"""<!doctype html>
<html>
<body>
  <iframe id="viewport" title="Responsive acceptance viewport" src="{fixture.as_uri()}" style="display:block;width:{width}px;height:900px;border:0"></iframe>
  <output id="responsiveProof"></output>
  <script>
    const frame = document.getElementById('viewport');
    const proof = document.getElementById('responsiveProof');
    window.addEventListener('message', (event) => {{
      if (event.source !== frame.contentWindow || !event.data || event.data.type !== 'responsive-proof') return;
      proof.dataset.clientWidth = String(event.data.clientWidth);
      proof.dataset.noPageOverflow = String(event.data.noPageOverflow);
      proof.dataset.navCount = String(event.data.navCount);
      proof.dataset.navWithinViewport = String(event.data.navWithinViewport);
      proof.dataset.statusFocusable = String(event.data.statusFocusable);
      proof.dataset.statusActive = String(event.data.statusActive);
      proof.dataset.statusCurrent = String(event.data.statusCurrent);
      proof.dataset.ready = 'true';
    }});
  </script>
</body>
</html>
"""
    )
    return harness


def test_real_shell_responsive_and_200_percent_zoom_equivalent(tmp_path: Path) -> None:
    fixture = _write_real_shell_fixture(tmp_path)
    # 720 CSS px is the effective layout width of a 1440 px desktop viewport at 200% browser zoom.
    # A visible vertical scrollbar may consume a small part of the iframe's declared width.
    for width in (320, 390, 412, 720, 1440):
        harness = _write_viewport_harness(tmp_path, fixture, width)
        rendered = _run_browser(harness.as_uri(), width=1600, height=1000)
        match = re.search(r'data-client-width="(\d+)"', rendered)
        assert match, rendered
        client_width = int(match.group(1))
        assert width - 20 <= client_width <= width, rendered
        assert 'data-no-page-overflow="true"' in rendered, rendered
        assert 'data-nav-count="5"' in rendered, rendered
        assert 'data-nav-within-viewport="true"' in rendered, rendered
        assert 'data-status-focusable="true"' in rendered, rendered
        assert 'data-status-active="true"' in rendered, rendered
        assert 'data-status-current="true"' in rendered, rendered
        assert 'data-ready="true"' in rendered, rendered
