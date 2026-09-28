from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"
INDEX = STATIC / "index.html"
APP_CSS = STATIC / "app.css"
ACCEPTED_UI_CSS = STATIC / "accepted_ui.css"


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the accessibility regression proof")


def _run_browser(uri: str, *, width: int = 900, height: int = 900, budget_ms: int = 1200) -> str:
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


def _write_real_shell_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "accessible-control-name-proof.html"
    html = INDEX.read_text()
    html = html.replace('href="/static/app.css"', f'href="{APP_CSS.as_uri()}"')
    html = html.replace('href="/static/accepted_ui.css"', f'href="{ACCEPTED_UI_CSS.as_uri()}"')
    html = re.sub(r'\s*<script[^>]+src="/static/[^"]+"[^>]*></script>', "", html)
    proof = """
  <output id="accessibilityProof"></output>
  <script>
    const proof = document.getElementById('accessibilityProof');
    const controls = [...document.querySelectorAll(
      'a[href], button, select, input, textarea, summary, [tabindex]:not([tabindex="-1"])'
    )];

    function normalizedText(value) {
      return String(value || '').replace(/\\s+/g, ' ').trim();
    }

    function referencedText(ids) {
      return normalizedText(
        String(ids || '')
          .split(/\\s+/)
          .filter(Boolean)
          .map((id) => document.getElementById(id)?.textContent || '')
          .join(' ')
      );
    }

    function labelText(element) {
      if (element.id) {
        const explicit = document.querySelector(`label[for="${CSS.escape(element.id)}"]`);
        if (explicit) return normalizedText(explicit.textContent);
      }
      const wrapping = element.closest('label');
      return wrapping ? normalizedText(wrapping.textContent) : '';
    }

    function controlName(element) {
      const ariaLabel = normalizedText(element.getAttribute('aria-label'));
      if (ariaLabel) return ariaLabel;
      const labelledBy = referencedText(element.getAttribute('aria-labelledby'));
      if (labelledBy) return labelledBy;
      const label = labelText(element);
      if (label) return label;
      if (element.matches('input[type="button"], input[type="submit"], input[type="reset"]')) {
        const value = normalizedText(element.value);
        if (value) return value;
      }
      const text = normalizedText(element.textContent);
      if (text) return text;
      return normalizedText(element.getAttribute('title'));
    }

    const unnamed = controls.filter((element) => !controlName(element));
    proof.dataset.controlCount = String(controls.length);
    proof.dataset.allNamed = String(controls.length > 0 && unnamed.length === 0);
    proof.dataset.unnamed = unnamed.map((element) => element.id || element.tagName.toLowerCase()).join(',');
    proof.dataset.ready = 'true';
  </script>
"""
    html = html.replace("</body>", proof + "\n</body>")
    fixture.write_text(html)
    return fixture


def test_real_shell_interactive_controls_have_accessible_names(tmp_path: Path) -> None:
    fixture = _write_real_shell_fixture(tmp_path)
    rendered = _run_browser(fixture.as_uri())

    assert 'data-ready="true"' in rendered, rendered
    assert 'data-all-named="true"' in rendered, rendered
    assert 'data-unnamed=""' in rendered, rendered


def test_accepted_ui_keeps_visible_keyboard_focus_contract() -> None:
    css = ACCEPTED_UI_CSS.read_text()
    assert "html[data-ui-theme] :focus-visible" in css
    assert "outline:2px solid var(--accent)" in css
    assert "outline-offset:3px" in css
