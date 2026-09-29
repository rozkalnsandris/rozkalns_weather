import importlib.util
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Route, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
LAB_PATH = ROOT / "tests" / "test_ui_performance_lab_browser.py"


def _load_lab_module():
    spec = importlib.util.spec_from_file_location("rozkalns_ui_performance_lab", LAB_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_network_failure_uses_stale_cache_without_erasing_observation_evidence() -> None:
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

            initial = {
                "temperature": page.locator("#heroTemperature").inner_text().strip(),
                "condition": page.locator("#heroCondition").inner_text().strip(),
                "feels": page.locator("#heroFeels").inner_text().strip(),
                "source": page.locator("#heroSource").inner_text().strip(),
                "humidity": page.locator("#detailHumidity").inner_text().strip(),
                "wind": page.locator("#detailWind").inner_text().strip(),
                "pressure": page.locator("#detailPressure").inner_text().strip(),
                "rain": page.locator("#detailRain").inner_text().strip(),
                "cloud": page.locator("#detailCloud").inner_text().strip(),
                "gust": page.locator("#detailGust").inner_text().strip(),
            }
            assert initial["temperature"] != "—°"
            assert initial["condition"] != "Observation unavailable"
            assert initial["source"]
            assert page.locator("#heroIcon svg").count() == 1

            current_failure_seen = {"value": False}

            def failed_current(route: Route) -> None:
                if urlparse(route.request.url).path != "/api/current":
                    route.continue_()
                    return
                current_failure_seen["value"] = True
                route.fulfill(
                    status=503,
                    content_type="application/json",
                    body='{"detail":"controlled current observation refresh failure"}',
                )

            page.route("**/api/current", failed_current)
            page.locator("#refreshOverview").click()

            page.wait_for_function(
                "() => document.querySelector('#currentState')?.dataset.state === 'stale'",
                timeout=7_500,
            )
            page.wait_for_function(
                "() => document.querySelector('#overviewTempState')?.dataset.state === 'fresh' && document.querySelector('#overviewPrecipState')?.dataset.state === 'fresh' && document.querySelector('#dailyState')?.dataset.state === 'fresh'",
                timeout=7_500,
            )
            assert current_failure_seen["value"] is True

            state = page.locator("#currentState")
            assert state.get_attribute("role") == "status"
            assert state.get_attribute("aria-live") == "polite"
            assert state.get_attribute("data-state") == "stale"
            assert "DWD observation is not current" in state.inner_text()
            assert "DWD current observation unavailable" not in state.inner_text()

            assert page.locator("#heroTemperature").inner_text().strip() == initial["temperature"]
            assert page.locator("#heroCondition").inner_text().strip() == initial["condition"]
            assert page.locator("#heroFeels").inner_text().strip() == initial["feels"]
            assert page.locator("#heroSource").inner_text().strip() == initial["source"]
            assert page.locator("#detailHumidity").inner_text().strip() == initial["humidity"]
            assert page.locator("#detailWind").inner_text().strip() == initial["wind"]
            assert page.locator("#detailPressure").inner_text().strip() == initial["pressure"]
            assert page.locator("#detailRain").inner_text().strip() == initial["rain"]
            assert page.locator("#detailCloud").inner_text().strip() == initial["cloud"]
            assert page.locator("#detailGust").inner_text().strip() == initial["gust"]
            assert page.locator("#heroIcon svg").count() == 1
            assert "not current" in page.locator("#heroUpdated").inner_text().lower()

            assert page.locator("#hourlyStrip .hour-card").count() > 0
            assert page.locator("#consumerHourlyChart svg").count() == 1
            assert page.locator("#dailyGrid").inner_text().strip() != "Daily forecast unavailable."
            assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")

            context.close()
            browser.close()
    finally:
        lab._stop_server(server, thread)
