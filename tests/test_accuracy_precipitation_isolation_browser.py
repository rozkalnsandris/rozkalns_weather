import importlib.util
from pathlib import Path

from playwright.sync_api import Route, expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
LAB_PATH = ROOT / "tests" / "test_accuracy_state_matrix_browser.py"


def _load_lab_module():
    spec = importlib.util.spec_from_file_location("rozkalns_accuracy_state_matrix", LAB_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_accuracy_keeps_temperature_summary_when_precipitation_calibration_fails() -> None:
    lab = _load_lab_module()
    server, thread = lab._start_server()
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    try:
        with sync_playwright() as playwright:
            browser = lab._launch(playwright)
            try:
                context = browser.new_context(
                    viewport={"width": 412, "height": 892},
                    service_workers="block",
                    is_mobile=True,
                )
                page = context.new_page()
                precipitation_failure_seen = {"value": False}

                def fail_precipitation(route: Route) -> None:
                    precipitation_failure_seen["value"] = True
                    route.fulfill(
                        status=503,
                        content_type="application/json",
                        body='{"detail":"controlled precipitation calibration outage"}',
                    )

                page.route("**/api/verification/precipitation**", fail_precipitation)
                page.goto(url, wait_until="load", timeout=15_000)
                page.locator('[data-view="accuracy"]').click()
                page.evaluate("() => { window.accuracy(30); }")

                expect(page.locator("#accuracyState")).to_have_class(
                    "surface-state state-fresh", timeout=5_000
                )
                assert precipitation_failure_seen["value"] is True
                expect(page.locator("#accuracyCohort")).to_be_enabled()
                expect(page.locator("#accuracyCohort option")).to_have_count(2)
                expect(page.locator("#accuracySummaryRows")).to_contain_text("1.40 °C")
                expect(page.locator("#accuracySummaryRows")).to_contain_text("1.20 °C")
                expect(page.locator("#calibrationTable")).to_have_text(
                    "Precipitation calibration unavailable."
                )
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
                )

                context.close()
            finally:
                browser.close()
    finally:
        lab._stop_server(server, thread)
