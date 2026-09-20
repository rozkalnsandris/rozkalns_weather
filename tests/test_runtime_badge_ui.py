import json
import subprocess
from pathlib import Path


RUNTIME_BADGE = Path("src/rozkalns_weather/static/runtime_badge.js")


def _derive(**state: object) -> str:
    script = f"""
const {{ deriveRuntimeBadge }} = require('./{RUNTIME_BADGE.as_posix()}');
process.stdout.write(JSON.stringify(deriveRuntimeBadge({json.dumps(state)})));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_runtime_badge_reports_ready_for_healthy_public_runtime() -> None:
    assert _derive(online=True, readinessOk=True, healthState="fresh") == "ready"


def test_runtime_badge_reports_degraded_for_non_fresh_or_not_ready_runtime() -> None:
    assert _derive(online=True, readinessOk=True, healthState="stale") == "degraded"
    assert _derive(online=True, readinessOk=False, healthState="fresh") == "degraded"


def test_runtime_badge_distinguishes_api_failure_and_offline() -> None:
    assert _derive(online=True, readinessOk=False, healthState="error", apiUnavailable=True) == "API unavailable"
    assert _derive(online=False, readinessOk=True, healthState="fresh", apiUnavailable=True) == "offline"


def test_public_only_home_unconfigured_does_not_drive_global_badge() -> None:
    # Extra/private-home state is intentionally irrelevant to the public runtime badge.
    assert _derive(
        online=True,
        readinessOk=True,
        healthState="fresh",
        homeConfigured=False,
    ) == "ready"


def test_index_loads_runtime_badge_controller_after_main_app() -> None:
    html = Path("src/rozkalns_weather/static/index.html").read_text()
    assert '/static/runtime_badge.js' in html
    assert html.index('/static/app.js') < html.index('/static/runtime_badge.js')
