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
    raise AssertionError(
        "A real Chromium-family browser is required for the hidden rendering regression proof"
    )


def _hero_state_contract() -> str:
    source = INDEX.read_text()
    match = re.search(
        r'<style id="overview-hero-state-contract">\s*(.*?)\s*</style>',
        source,
        flags=re.DOTALL,
    )
    assert match is not None, "overview hero-state inline rendering contract is missing"
    return match.group(1)


def test_hidden_hero_state_has_no_rendered_box_while_degraded_states_remain_visible(
    tmp_path: Path,
) -> None:
    template = """<!doctype html>
<html lang="en" data-ui-theme="light">
<head>
  <meta charset="utf-8">
  <link rel="stylesheet" href="__APP_CSS__">
  <link rel="stylesheet" href="__ACCEPTED_UI_CSS__">
  <style id="overview-hero-state-contract">__HERO_STATE_CONTRACT__</style>
</head>
<body>
  <section class="weather-hero">
    <div id="fresh" class="surface-state state-fresh hero-state" role="status">DWD observation current</div>
    <div id="stale" class="surface-state state-stale hero-state" role="status">STALE · DWD observation is not current</div>
    <div id="error" class="surface-state state-error hero-state" role="status">ERROR · DWD observation provider degraded</div>
  </section>
  <output id="proof"></output>
  <script>
    function snapshot(theme) {
      document.documentElement.dataset.uiTheme = theme;
      const fresh = document.getElementById("fresh");
      const stale = document.getElementById("stale");
      const error = document.getElementById("error");

      fresh.hidden = true;
      fresh.setAttribute("aria-hidden", "true");
      stale.hidden = false;
      stale.removeAttribute("aria-hidden");
      error.hidden = false;
      error.removeAttribute("aria-hidden");

      const freshStyle = getComputedStyle(fresh);
      const staleStyle = getComputedStyle(stale);
      const errorStyle = getComputedStyle(error);
      const freshRect = fresh.getBoundingClientRect();
      const staleRect = stale.getBoundingClientRect();
      const errorRect = error.getBoundingClientRect();

      return {
        freshNonRendered:
          fresh.hidden &&
          fresh.getAttribute("aria-hidden") === "true" &&
          freshStyle.display === "none" &&
          freshRect.width === 0 &&
          freshRect.height === 0,
        staleVisible:
          !stale.hidden &&
          staleStyle.display !== "none" &&
          staleRect.width > 0 &&
          staleRect.height > 0,
        errorVisible:
          !error.hidden &&
          errorStyle.display !== "none" &&
          errorRect.width > 0 &&
          errorRect.height > 0,
      };
    }

    requestAnimationFrame(() => {
      const light = snapshot("light");
      const dark = snapshot("dark");
      const proof = document.getElementById("proof");
      proof.dataset.lightFreshNonRendered = String(light.freshNonRendered);
      proof.dataset.lightStaleVisible = String(light.staleVisible);
      proof.dataset.lightErrorVisible = String(light.errorVisible);
      proof.dataset.darkFreshNonRendered = String(dark.freshNonRendered);
      proof.dataset.darkStaleVisible = String(dark.staleVisible);
      proof.dataset.darkErrorVisible = String(dark.errorVisible);
      document.documentElement.dataset.proofReady = "true";
    });
  </script>
</body>
</html>
"""
    fixture = tmp_path / "hidden-rendering-proof.html"
    fixture.write_text(
        template.replace("__APP_CSS__", APP_CSS.as_uri())
        .replace("__ACCEPTED_UI_CSS__", ACCEPTED_UI_CSS.as_uri())
        .replace("__HERO_STATE_CONTRACT__", _hero_state_contract())
    )

    completed = subprocess.run(
        [
            _browser_binary(),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            "--virtual-time-budget=1000",
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
    assert 'data-proof-ready="true"' in rendered
    for attribute in (
        "data-light-fresh-non-rendered",
        "data-light-stale-visible",
        "data-light-error-visible",
        "data-dark-fresh-non-rendered",
        "data-dark-stale-visible",
        "data-dark-error-visible",
    ):
        assert f'{attribute}="true"' in rendered, rendered
