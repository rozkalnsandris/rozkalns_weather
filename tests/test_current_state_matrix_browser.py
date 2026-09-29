import importlib.util
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Route, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
LAB_PATH = ROOT / "tests" / "test_ui_performance_lab_browser.py"
CURRENT_CACHE_KEY = "rozkalns-weather:pwa-cache:v1:current"


def _load_lab_module():
    spec = importlib.util.spec_from_file_location("rozkalns_ui_performance_lab", LAB_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_shell_current_hard_error_clears_previous_observation_evidence() -> None:
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
                viewport={"width": 412, "height": 892},
                service_workers="block",
                is_mobile=True,
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            lab._wait_for_forecast(page)

            page.wait_for_function(
                "() => document.querySelector('#currentState')?.dataset.state === 'fresh'",
                timeout=7_500,
            )
            initial_icon = page.locator("#heroIcon").inner_text().strip()
            initial_feels = page.locator("#heroFeels").inner_text().strip()
            initial_source = page.locator("#heroSource").inner_text().strip()
            detail_ids = [
                "detailHumidity",
                "detailWind",
                "detailPressure",
                "detailRain",
                "detailCloud",
                "detailGust",
            ]
            initial_details = {item: page.locator(f"#{item}").inner_text().strip() for item in detail_ids}
            assert initial_feels
            assert initial_source
            assert any(value != "—" for value in initial_details.values())

            page.evaluate("key => localStorage.removeItem(key)", CURRENT_CACHE_KEY)
            current_failure_seen = {"value": False}

            def failed_current(route: Route) -> None:
                if urlparse(route.request.url).path != "/api/current":
                    route.continue_()
                    return
                current_failure_seen["value"] = True
                route.fulfill(
                    status=503,
                    content_type="application/json",
                    body='{"detail":"controlled current observation failure"}',
                )

            page.route("**/api/current", failed_current)
            page.locator("#refreshOverview").click()

            page.wait_for_function(
                "() => document.querySelector('#currentState')?.dataset.state === 'error'",
                timeout=7_500,
            )
            page.wait_for_function(
                "() => document.querySelector('#overviewTempState')?.dataset.state === 'fresh' && document.querySelector('#overviewPrecipState')?.dataset.state === 'fresh' && document.querySelector('#dailyState')?.dataset.state === 'fresh'",
                timeout=7_500,
            )
            assert current_failure_seen["value"] is True

            current_state = page.locator("#currentState")
            assert current_state.get_attribute("role") == "alert"
            assert current_state.get_attribute("aria-live") == "assertive"
            assert "DWD current observation unavailable" in current_state.inner_text()
            assert "503 Service Unavailable" in current_state.inner_text()

            assert page.locator("#heroTemperature").inner_text().strip() == "—°"
            assert page.locator("#heroCondition").inner_text().strip() == "Observation unavailable"
            assert page.locator("#heroUpdated").inner_text().strip() == "Current observation unavailable"
            assert page.locator("#heroIcon").inner_text().strip() == "◌"
            assert page.locator("#heroFeels").inner_text().strip() == "No current DWD observation available"
            assert page.locator("#heroSource").inner_text().strip() == "DWD current observation unavailable"
            assert page.locator("#heroIcon").inner_text().strip() != initial_icon
            assert page.locator("#heroFeels").inner_text().strip() != initial_feels
            assert page.locator("#heroSource").inner_text().strip() != initial_source

            for item in detail_ids:
                assert page.locator(f"#{item}").inner_text().strip() == "—"
                if initial_details[item] != "—":
                    assert page.locator(f"#{item}").inner_text().strip() != initial_details[item]

            assert page.locator("#hourlyStrip .hour-card").count() > 0
            assert page.locator("#consumerHourlyChart svg").count() == 1
            assert page.locator("#dailyGrid").inner_text().strip() != "Daily forecast unavailable."
            assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")

            context.close()
            browser.close()
    finally:
        lab._stop_server(server, thread)
