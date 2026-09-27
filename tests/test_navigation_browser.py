from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"
INDEX = STATIC / "index.html"
NAVIGATION = STATIC / "navigation_v1.js"
SW = STATIC / "sw.js"


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the navigation regression proof")


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
    assert 'const CACHE = "rozkalns-weather-v16"' in sw
    assert '"/static/navigation_v1.js"' in sw


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

    completed = subprocess.run(
        [
            _browser_binary(),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            "--virtual-time-budget=1500",
            "--dump-dom",
            fixture.as_uri() + "#models",
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
    assert 'data-direct="true"' in rendered, rendered
    assert 'data-status="true"' in rendered, rendered
    assert 'data-back="true"' in rendered, rendered
