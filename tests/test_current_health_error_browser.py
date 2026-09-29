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

            immediate = page.evaluate(
                """
                async (dwdHealth) => {
                  const response = await fetch('/api/current', { cache: 'no-store' });
                  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
                  const payload = await response.json();
                  const result = {
                    payload,
                    source: 'network',
                    cached_at_utc: new Date().toISOString(),
                    error: null,
                  };
                  window.renderCurrent(result, { dwd_observations: dwdHealth });
                  const state = document.querySelector('#currentState');
                  const text = (selector) => document.querySelector(selector)?.textContent?.trim() ?? null;
                  return {
                    state: state?.dataset.state ?? null,
                    stateText: state?.textContent?.trim() ?? null,
                    role: state?.getAttribute('role') ?? null,
                    ariaLive: state?.getAttribute('aria-live') ?? null,
                    temperature: text('#heroTemperature'),
                    condition: text('#heroCondition'),
                    feels: text('#heroFeels'),
                    source: text('#heroSource'),
                    humidity: text('#detailHumidity'),
                    pressure: text('#detailPressure'),
                    iconCount: document.querySelectorAll('#heroIcon svg').length,
                  };
                }
                """,
                degraded_observation_health,
            )

            assert immediate["state"] == "error", immediate
            assert immediate["role"] == "alert", immediate
            assert immediate["ariaLive"] == "assertive", immediate
            assert "DWD observation provider degraded" in immediate["stateText"], immediate
            assert "DWD current observation unavailable" not in immediate["stateText"], immediate
            assert immediate["temperature"] == initial["temperature"], immediate
            assert immediate["condition"] == initial["condition"], immediate
            assert immediate["feels"] == initial["feels"], immediate
            assert immediate["source"] == initial["source"], immediate
            assert immediate["humidity"] == initial["humidity"], immediate
            assert immediate["pressure"] == initial["pressure"], immediate
            assert immediate["iconCount"] == 1, immediate

            page.wait_for_timeout(250)
            settled = page.evaluate(
                """
                () => {
                  const state = document.querySelector('#currentState');
                  return {
                    state: state?.dataset.state ?? null,
                    stateText: state?.textContent?.trim() ?? null,
                    role: state?.getAttribute('role') ?? null,
                    ariaLive: state?.getAttribute('aria-live') ?? null,
                  };
                }
                """
            )
            assert settled["state"] == "error", {"immediate": immediate, "settled": settled}
            assert "DWD observation provider degraded" in settled["stateText"], {
                "immediate": immediate,
                "settled": settled,
            }

            assert page.locator("#overviewTempState").get_attribute("data-state") == "fresh"
            assert page.locator("#overviewPrecipState").get_attribute("data-state") == "fresh"
            assert page.locator("#dailyState").get_attribute("data-state") == "fresh"
            assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")

            context.close()
            browser.close()
    finally:
        lab._stop_server(server, thread)
