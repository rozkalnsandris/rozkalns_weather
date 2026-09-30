import importlib.util
import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
LAB_PATH = ROOT / "tests" / "test_ui_performance_lab_browser.py"


def _load_lab_module():
    spec = importlib.util.spec_from_file_location("rozkalns_ui_performance_lab", LAB_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WARNING_PAYLOAD = {
    "authority": "DWD",
    "official": True,
    "kind": "official_warning",
    "state": "no_active_alerts",
    "alerts": [],
    "retrieved_at_utc": "2026-09-30T12:00:00Z",
    "reference_location": {"id": "station_05480", "label": "DWD CDC Werl 05480"},
    "source_attribution": "DWD deterministic fixture",
}

RADAR_PAYLOAD = {
    "state": "frames_present",
    "frames": [
        {
            "timestamp": "2026-09-30T11:55:00Z",
            "kind": "radar_observed",
            "source": "DWD RADOLAN observed",
        },
        {
            "timestamp": "2026-09-30T12:30:00Z",
            "kind": "radar_nowcast",
            "source": "DWD radar nowcast",
        },
    ],
    "map_contract": {
        "rendering_contract": {
            "state": "metadata_only",
            "raster_rendering_available": False,
            "reason_code": "RADAR_RASTER_CONTRACT_PENDING",
        }
    },
}


@pytest.mark.parametrize(
    ("viewport", "is_mobile"),
    [
        ({"width": 1440, "height": 900}, False),
        ({"width": 412, "height": 892}, True),
    ],
    ids=["desktop-1440x900", "galaxy-a55-412x892"],
)
def test_safety_view_uses_consistent_english_copy(viewport: dict[str, int], is_mobile: bool) -> None:
    lab = _load_lab_module()
    server, thread = lab._start_server()
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=lab._browser_binary(),
                headless=True,
                args=["--no-sandbox", "--disable-gpu"],
            )
            context = browser.new_context(
                viewport=viewport,
                service_workers="block",
                is_mobile=is_mobile,
            )
            page = context.new_page()
            page.route(
                "**/api/warnings",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(WARNING_PAYLOAD),
                ),
            )
            page.route(
                "**/api/radar",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(RADAR_PAYLOAD),
                ),
            )

            page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            lab._wait_for_forecast(page)
            page.locator('button[data-view="safety"]').click()
            page.wait_for_function(
                "() => document.querySelector('#warningsState')?.dataset.warningState === 'clear'",
                timeout=7_500,
            )
            page.wait_for_function(
                "() => document.querySelector('#radarState')?.dataset.state === 'fresh'",
                timeout=7_500,
            )

            assert page.locator("html").get_attribute("lang") == "en"
            safety_text = page.locator("#safety").inner_text()
            assert "DWD warning layer is authoritative and separate from model forecasts." in safety_text
            assert "In public-only mode, warnings use the public DWD CDC Werl 05480 reference point" in safety_text
            assert "Technical warning JSON" in safety_text
            assert "Authority: DWD" in safety_text
            assert "Radar observed/nowcast is not a model forecast." in safety_text
            assert "Latest observed" in safety_text
            assert "Nowcast" in safety_text

            lower = safety_text.lower()
            for fragment in (
                "slānis",
                "autoritatīvs",
                "atdalīts",
                "režīmā",
                "publisko",
                "precīzas",
                "koordinātas",
                "netiek izpaustas",
                "nav model forecast",
                "reference punktu",
                "privāta home",
            ):
                assert fragment not in lower

            context.close()
            browser.close()
    finally:
        lab._stop_server(server, thread)
