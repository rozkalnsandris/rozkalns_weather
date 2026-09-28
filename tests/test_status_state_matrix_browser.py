import importlib.util
import json
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


def test_real_shell_status_keeps_card_state_in_sync_through_refresh_offline_and_error() -> None:
    lab = _load_lab_module()
    server, thread = lab._start_server()
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    public_providers = [
        {
            "id": "dwd_observations",
            "model_name": "DWD CDC observations",
            "state": "success",
            "ingest_state": "success",
            "freshness_state": "fresh",
            "last_retrieved_at_utc": "2026-09-28T20:00:00Z",
        },
        {
            "id": "dwd_mosmix_l",
            "model_name": "DWD MOSMIX-L",
            "state": "success",
            "ingest_state": "success",
            "freshness_state": "fresh",
            "last_retrieved_at_utc": "2026-09-28T20:00:00Z",
        },
        {
            "id": "icon_d2",
            "model_name": "ICON-D2",
            "state": "success",
            "ingest_state": "success",
            "freshness_state": "fresh",
            "last_retrieved_at_utc": "2026-09-28T20:00:00Z",
        },
        {
            "id": "ecmwf_ifs",
            "model_name": "ECMWF IFS",
            "state": "success",
            "ingest_state": "success",
            "freshness_state": "fresh",
            "last_retrieved_at_utc": "2026-09-28T20:00:00Z",
        },
        {
            "id": "ecmwf_aifs",
            "model_name": "ECMWF AIFS",
            "state": "success",
            "ingest_state": "success",
            "freshness_state": "fresh",
            "last_retrieved_at_utc": "2026-09-28T20:00:00Z",
        },
        {
            "id": "weathernext3",
            "model_name": "WeatherNext 3",
            "state": "success",
            "ingest_state": "ready",
            "freshness_state": "fresh",
        },
    ]

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

            def fresh_status_api(route: Route) -> None:
                parsed = urlparse(route.request.url)
                query = parse_qs(parsed.query)
                if parsed.path == "/api/health/providers":
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({"providers": public_providers}),
                    )
                    return
                if parsed.path == "/api/hourly" and query.get("providers", [""])[0] == "weathernext3":
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "series": [
                                    {
                                        "provider": "weathernext3",
                                        "value": 12.3,
                                        "valid_time_utc": "2026-09-28T21:00:00Z",
                                        "init_time_utc": "2026-09-28T18:00:00Z",
                                        "lead_hours": 3,
                                        "retrieved_at_utc": "2026-09-28T20:05:00Z",
                                        "statistic": "mean",
                                        "model_version": "wn3-status-test",
                                    }
                                ]
                            }
                        ),
                    )
                    return
                if parsed.path == "/api/verification/summary":
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "verification_ready": True,
                                "truth_quality": {"reason_codes": []},
                                "providers": {"weathernext3": {"overall": {"n": 12}}},
                                "common_sample_slices": [
                                    {
                                        "provider": "weathernext3",
                                        "sample_sufficiency_state": "sufficient",
                                    }
                                ],
                            }
                        ),
                    )
                    return
                route.continue_()

            page.route("**/api/**", fresh_status_api)
            page.locator('button[data-view="status"]').click()
            page.wait_for_function(
                "() => document.querySelector('#statusWeatherNextState')?.dataset.state === 'fresh'",
                timeout=7_500,
            )

            card = page.locator("#statusWeatherNext")
            state = page.locator("#statusWeatherNextState")
            assert card.get_attribute("data-state") == "fresh"
            assert state.get_attribute("role") == "status"
            assert state.get_attribute("aria-live") == "polite"
            assert "Available · 12.3°" in page.locator("#statusWeatherNextForecast").inner_text()
            assert "Ready · 1 sufficient cohort" in page.locator("#statusWeatherNextVerification").inner_text()

            page.unroute("**/api/**", fresh_status_api)
            server.api_delay_seconds = 0.45
            page.select_option("#forecastLocation", "station_10416")
            page.wait_for_function(
                "() => document.querySelector('#statusWeatherNextState')?.dataset.state === 'loading'",
                timeout=2_000,
            )
            assert card.get_attribute("data-state") == "loading"

            page.wait_for_function(
                "() => document.querySelector('#statusWeatherNextState')?.dataset.state === 'stale'",
                timeout=7_500,
            )
            assert card.get_attribute("data-state") == "stale"
            assert "No genuine data · access pending" in page.locator("#statusWeatherNextForecast").inner_text()

            page.evaluate("window.dispatchEvent(new Event('offline'))")
            page.wait_for_function(
                "() => document.querySelector('#statusWeatherNextState')?.dataset.state === 'offline'",
                timeout=2_000,
            )
            assert card.get_attribute("data-state") == "offline"
            assert "last-known and not current" in state.inner_text()

            page.evaluate(
                """() => {
                  for (const key of Object.keys(localStorage)) {
                    if (key.startsWith('rozkalns-weather:pwa-cache:v1:status-')) localStorage.removeItem(key);
                  }
                }"""
            )
            server.api_delay_seconds = 0.05
            server.api_mode = "fail"
            page.evaluate("window.dispatchEvent(new Event('online'))")
            page.wait_for_function(
                "() => document.querySelector('#statusWeatherNextState')?.dataset.state === 'error'",
                timeout=7_500,
            )
            assert card.get_attribute("data-state") == "error"
            assert "Forecast availability unavailable" in page.locator("#statusWeatherNextForecast").inner_text()
            assert "Verification readiness unavailable" in page.locator("#statusWeatherNextVerification").inner_text()
            assert "Public provider status unavailable" in page.locator("#statusSources").inner_text()
            assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")

            context.close()
            browser.close()
    finally:
        lab._stop_server(server, thread)
