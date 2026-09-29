import importlib.util
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
LAB_PATH = ROOT / "tests" / "test_ui_performance_lab_browser.py"


def _load_lab_module():
    spec = importlib.util.spec_from_file_location("rozkalns_ui_performance_lab", LAB_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_health_error_keeps_available_current_observation_evidence() -> None:
    lab = _load_lab_module()
    server, thread = lab._start_server()
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    degraded_observation_health = {
        "state": "error",
        "ingest_state": "error",
        "freshness_state": "error",
        "failure_domain": "controlled_test",
        "reason_code": "controlled_provider_health_error",
    }

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
                "pressure": page.locator("#detailPressure").inner_text().strip(),
            }
            assert initial["temperature"] == "13°"
            assert initial["condition"] != "Observation unavailable"
            assert initial["feels"] and initial["feels"] != "No current DWD observation available"
            assert initial["source"] and initial["source"] != "DWD current observation unavailable"
            assert initial["humidity"] == "72%"
            assert initial["pressure"] == "1015 hPa"
            assert page.locator("#heroIcon svg").count() == 1

            page.evaluate(
                """
                async (dwdHealth) => {
                  const result = await window.apiWithFallback('/api/current', 'current');
                  window.renderCurrent(result, { dwd_observations: dwdHealth });
                }
                """,
                degraded_observation_health,
            )

            page.wait_for_function(
                "() => document.querySelector('#currentState')?.dataset.state === 'error' && document.querySelector('#currentState')?.textContent.includes('provider health reports an error')",
                timeout=7_500,
            )

            current_state = page.locator("#currentState")
            assert current_state.get_attribute("role") == "alert"
            assert current_state.get_attribute("aria-live") == "assertive"
            assert "Latest DWD observation" in current_state.inner_text()
            assert "provider health reports an error" in current_state.inner_text()
            assert "DWD current observation unavailable" not in current_state.inner_text()

            assert page.locator("#heroTemperature").inner_text().strip() == initial["temperature"]
            assert page.locator("#heroCondition").inner_text().strip() == initial["condition"]
            assert page.locator("#heroFeels").inner_text().strip() == initial["feels"]
            assert page.locator("#heroSource").inner_text().strip() == initial["source"]
            assert page.locator("#detailHumidity").inner_text().strip() == initial["humidity"]
            assert page.locator("#detailPressure").inner_text().strip() == initial["pressure"]
            assert page.locator("#heroIcon svg").count() == 1

            assert page.locator("#overviewTempState").get_attribute("data-state") == "fresh"
            assert page.locator("#overviewPrecipState").get_attribute("data-state") == "fresh"
            assert page.locator("#dailyState").get_attribute("data-state") == "fresh"
            assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")

            context.close()
            browser.close()
    finally:
        lab._stop_server(server, thread)
