from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
TIME_JS = ROOT / "src" / "rozkalns_weather" / "static" / "time_semantics.js"


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the DST regression proof")


def _run_browser(uri: str, *, budget_ms: int = 800) -> str:
    completed = subprocess.run(
        [
            _browser_binary(),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            "--window-size=800,600",
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


def _write_dst_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "time-semantics-dst-proof.html"
    fixture.write_text(
        f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>DST proof</title></head>
<body>
  <output id="dstProof"></output>
  <script src="{TIME_JS.as_uri()}"></script>
  <script>
    const autumnFirst = globalThis.berlinLocalIdentity('2026-10-25T00:30:00Z');
    const autumnSecond = globalThis.berlinLocalIdentity('2026-10-25T01:30:00Z');
    const springBefore = globalThis.berlinLocalIdentity('2026-03-29T00:30:00Z');
    const springAfter = globalThis.berlinLocalIdentity('2026-03-29T01:30:00Z');
    const proof = document.getElementById('dstProof');

    proof.dataset.autumnClock = `${{autumnFirst.localClock}}|${{autumnSecond.localClock}}`;
    proof.dataset.autumnOffsetsPresent = String(Boolean(autumnFirst.offset && autumnSecond.offset));
    proof.dataset.autumnOffsetsDistinct = String(autumnFirst.offset !== autumnSecond.offset);
    proof.dataset.autumnIdentitiesDistinct = String(autumnFirst.displayIdentity !== autumnSecond.displayIdentity);
    proof.dataset.autumnFormattedDistinct = String(
      globalThis.formatLocalTime('2026-10-25T00:30:00Z') !== globalThis.formatLocalTime('2026-10-25T01:30:00Z')
    );
    proof.dataset.springClock = `${{springBefore.localClock}}|${{springAfter.localClock}}`;
    proof.dataset.ready = 'true';
  </script>
</body>
</html>
"""
    )
    return fixture


def test_browser_distinguishes_repeated_autumn_hour_and_skips_spring_gap(tmp_path: Path) -> None:
    fixture = _write_dst_fixture(tmp_path)
    rendered = _run_browser(fixture.as_uri())

    assert 'data-ready="true"' in rendered, rendered
    assert 'data-autumn-clock="02:30:00|02:30:00"' in rendered, rendered
    assert 'data-autumn-offsets-present="true"' in rendered, rendered
    assert 'data-autumn-offsets-distinct="true"' in rendered, rendered
    assert 'data-autumn-identities-distinct="true"' in rendered, rendered
    assert 'data-autumn-formatted-distinct="true"' in rendered, rendered
    assert 'data-spring-clock="01:30:00|03:30:00"' in rendered, rendered
