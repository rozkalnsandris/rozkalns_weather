import importlib.util
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Route, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
LAB_PATH = ROOT / "tests" / "test_ui_performance_lab_browser.py"


def _load_lab_module():
    spec = importlib.util.spec_from_file_location("rozkalns_ui_performance_lab", LAB_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_shell_location_change_clears_previous_daily_after_daily_failure() -> None:
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
                "() => document.querySelector('#dailyState')?.dataset.state === 'fresh'",
                timeout=7_500,
            )
            initial_daily = page.locator("#dailyGrid").inner_text().strip()
            initial_high_low = page.locator("#heroHighLow").inner_text().strip()
            assert initial_daily
            assert initial_high_low
            assert initial_high_low != "H —° · L —°"

            current_daily_seen = {"value": False}

            def degraded_daily(route: Route) -> None:
                parsed = urlparse(route.request.url)
                query = parse_qs(parsed.query)
                if parsed.path != "/api/daily" or query.get("location_id", [""])[0] != "station_10416":
                    route.continue_()
                    return
                current_daily_seen["value"] = True
                route.fulfill(
                    status=503,
                    content_type="application/json",
                    body='{"detail":"controlled daily forecast failure"}',
                )

            page.route("**/api/daily**", degraded_daily)
            page.locator('button[data-view="status"]').click()
            page.select_option("#forecastLocation", "station_10416")

            page.wait_for_function(
                "() => document.querySelector('#dailyState')?.dataset.state === 'error'",
                timeout=7_500,
            )
            page.wait_for_function(
                "() => document.querySelector('#overviewTempState')?.dataset.state === 'fresh' && document.querySelector('#overviewPrecipState')?.dataset.state === 'fresh'",
                timeout=7_500,
            )
            assert current_daily_seen["value"] is True

            page.locator('button[data-view="overview"]').click()
            daily_state = page.locator("#dailyState")

            assert daily_state.get_attribute("role") == "alert"
            assert daily_state.get_attribute("aria-live") == "assertive"
            assert "Daily forecast unavailable" in daily_state.inner_text()
            assert "503 Service Unavailable" in daily_state.inner_text()

            daily_text = page.locator("#dailyGrid").inner_text().strip()
            assert daily_text == "Daily forecast unavailable."
            assert initial_daily not in daily_text
            assert page.locator("#heroHighLow").inner_text().strip() == "H —° · L —°"
            assert initial_high_low != page.locator("#heroHighLow").inner_text().strip()

            assert page.locator("#hourlyStrip .hour-card").count() > 0
            assert page.locator("#consumerHourlyChart svg").count() == 1
            assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")

            context.close()
            browser.close()
    finally:
        lab._stop_server(server, thread)
