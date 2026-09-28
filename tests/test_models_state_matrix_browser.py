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


def test_real_shell_location_change_does_not_leave_previous_models_chart_after_partial_failure() -> None:
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

            page.locator('button[data-view="models"]').click()
            page.wait_for_function(
                "() => document.querySelector('#modelsTempState')?.dataset.state === 'fresh'",
                timeout=7_500,
            )
            assert page.locator("#modelsChart svg").count() == 1
            assert page.locator("#modelsPrecip svg").count() == 1

            def degraded_hourly(route: Route) -> None:
                parsed = urlparse(route.request.url)
                query = parse_qs(parsed.query)
                if parsed.path != "/api/hourly" or query.get("location_id", [""])[0] != "station_10416":
                    route.continue_()
                    return
                variable = query.get("variable", [""])[0]
                if variable == "temperature_2m":
                    route.fulfill(
                        status=503,
                        content_type="application/json",
                        body='{"detail":"controlled Models temperature failure"}',
                    )
                    return
                route.continue_()

            page.route("**/api/hourly**", degraded_hourly)
            page.locator('button[data-view="status"]').click()
            page.select_option("#forecastLocation", "station_10416")

            page.wait_for_function(
                "() => document.querySelector('#modelsTempState')?.dataset.state === 'error'",
                timeout=7_500,
            )
            page.wait_for_function(
                "() => document.querySelector('#modelsPrecipState')?.dataset.state === 'fresh'",
                timeout=7_500,
            )

            page.locator('button[data-view="models"]').click()
            labels = page.locator("#models .forecast-location-label").all_inner_texts()
            assert labels and all("10416" in label for label in labels)

            temp_state = page.locator("#modelsTempState")
            precip_state = page.locator("#modelsPrecipState")
            assert temp_state.get_attribute("role") == "alert"
            assert temp_state.get_attribute("aria-live") == "assertive"
            assert "Temperature forecast unavailable" in temp_state.inner_text()
            assert "controlled Models temperature failure" in temp_state.inner_text()

            assert page.locator("#modelsChart svg").count() == 0
            assert "Temperature forecast unavailable" in page.locator("#modelsChart").inner_text()

            assert precip_state.get_attribute("role") == "status"
            assert precip_state.get_attribute("aria-live") == "polite"
            assert page.locator("#modelsPrecip svg").count() == 1

            context.close()
            browser.close()
    finally:
        lab._stop_server(server, thread)
