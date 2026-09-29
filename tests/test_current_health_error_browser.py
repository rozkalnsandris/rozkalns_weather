import importlib.util
import json
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


def test_provider_health_error_keeps_available_current_observation_evidence() -> None:
    lab = _load_lab_module()
    server, thread = lab._start_server()
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    degraded_health = {
        "home": {"configured": False},
        "providers": [
            {
                "id": "dwd_observations",
                "model_name": "DWD CDC observations",
                "state": "error",
                "ingest_state": "error",
                "freshness_state": "error",
                "failure_domain": "controlled_test",
                "reason_code": "controlled_provider_health_error",
            },
            {
                "id": "icon_d2",
                "model_name": "ICON-D2",
                "state": "success",
                "ingest_state": "success",
                "freshness_state": "fresh",
            },
            {
                "id": "ecmwf_ifs",
                "model_name": "ECMWF IFS",
                "state": "success",
                "ingest_state": "success",
                "freshness_state": "fresh",
            },
            {
                "id": "ecmwf_aifs",
                "model_name": "ECMWF AIFS",
                "state": "success",
                "ingest_state": "success",
                "freshness_state": "fresh",
            },
            {
                "id": "weathernext3",
                "model_name": "WeatherNext 3",
                "state": "access_pending",
                "ingest_state": "access_pending",
                "freshness_state": "not_ingested",
            },
        ],
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

            assert page.locator("#heroTemperature").inner_text().strip() == "13°"
            assert "Observed" in page.locator("#heroFeels").inner_text()
            assert "DWD CDC 05480" in page.locator("#heroSource").inner_text()
            assert page.locator("#detailHumidity").inner_text().strip() == "72%"
            assert page.locator("#detailPressure").inner_text().strip() == "1015 hPa"
            assert page.locator("#heroIcon svg").count() == 1

            health_failure_seen = {"value": False}

            def degraded_health_route(route: Route) -> None:
                if urlparse(route.request.url).path != "/api/health/providers":
                    route.continue_()
                    return
                health_failure_seen["value"] = True
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(degraded_health),
                )

            page.route("**/api/health/providers", degraded_health_route)
            page.locator("#refreshOverview").click()

            page.wait_for_function(
                "() => document.querySelector('#currentState')?.dataset.state === 'error' && document.querySelector('#currentState')?.textContent.includes('provider health reports an error')",
                timeout=7_500,
            )
            assert health_failure_seen["value"] is True

            current_state = page.locator("#currentState")
            assert current_state.get_attribute("role") == "alert"
            assert current_state.get_attribute("aria-live") == "assertive"
            assert "Latest DWD observation" in current_state.inner_text()
            assert "provider health reports an error" in current_state.inner_text()
            assert "DWD current observation unavailable" not in current_state.inner_text()

            assert page.locator("#heroTemperature").inner_text().strip() == "13°"
            assert page.locator("#heroCondition").inner_text().strip() != "Observation unavailable"
            assert "Observed" in page.locator("#heroFeels").inner_text()
            assert "DWD CDC 05480" in page.locator("#heroSource").inner_text()
            assert page.locator("#detailHumidity").inner_text().strip() == "72%"
            assert page.locator("#detailPressure").inner_text().strip() == "1015 hPa"
            assert page.locator("#heroIcon svg").count() == 1

            assert page.locator("#overviewTempState").get_attribute("data-state") == "fresh"
            assert page.locator("#overviewPrecipState").get_attribute("data-state") == "fresh"
            assert page.locator("#dailyState").get_attribute("data-state") == "fresh"
            assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")

            context.close()
            browser.close()
    finally:
        lab._stop_server(server, thread)
