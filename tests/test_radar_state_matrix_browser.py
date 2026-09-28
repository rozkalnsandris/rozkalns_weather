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


def _radar_payload() -> dict[str, object]:
    return {
        "state": "frames_present",
        "frames": [
            {
                "timestamp": "2026-09-28T11:55:00Z",
                "kind": "radar_observed",
                "source": "DWD RADOLAN observed",
            },
            {
                "timestamp": "2026-09-28T12:30:00Z",
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


def test_real_shell_radar_fresh_stale_and_error_states_keep_controls_honest() -> None:
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

            page.evaluate(
                """payload => {
                  window.__radarMode = 'fresh';
                  window.__radarCalls = 0;
                  window.__radarPayload = payload;
                  window.apiWithFallback = async (url, key) => {
                    if (url !== '/api/radar' || key !== 'safety-radar') {
                      throw new Error(`unexpected request: ${url} ${key}`);
                    }
                    window.__radarCalls += 1;
                    if (window.__radarMode === 'error') {
                      throw new Error('controlled radar refresh failure');
                    }
                    return {
                      payload: window.__radarPayload,
                      source: window.__radarMode === 'stale' ? 'stale-cache' : 'network',
                      cached_at_utc: '2026-09-28T12:00:00Z',
                      error: window.__radarMode === 'stale' ? 'controlled live refresh failure' : null,
                    };
                  };
                }""",
                _radar_payload(),
            )

            page.locator('button[data-view="safety"]').click()
            page.wait_for_function(
                "() => document.querySelector('#radarState')?.dataset.state === 'fresh'",
                timeout=7_500,
            )

            radar_output = page.locator("#radarOutput")
            radar_state = page.locator("#radarState")
            refresh = page.locator("#loadRadar")

            fresh_text = radar_output.inner_text()
            assert "Latest observed" in fresh_text
            assert "DWD RADOLAN observed" in fresh_text
            assert "Nowcast" in fresh_text
            assert "DWD radar nowcast" in fresh_text
            assert refresh.is_enabled()
            assert radar_output.get_attribute("aria-busy") == "false"
            assert page.evaluate("window.__radarCalls") == 1

            page.evaluate("window.__radarMode = 'stale'")
            refresh.click()
            page.wait_for_function(
                "() => document.querySelector('#radarState')?.dataset.state === 'stale'",
                timeout=7_500,
            )

            stale_text = radar_output.inner_text()
            assert "Latest observed" in stale_text
            assert "DWD RADOLAN observed" in stale_text
            assert "Nowcast" in stale_text
            assert "DWD radar nowcast" in stale_text
            assert "retained timestamps" in radar_state.inner_text().lower()
            assert refresh.is_enabled()
            assert radar_output.get_attribute("aria-busy") == "false"
            assert page.evaluate("window.__radarCalls") == 2

            page.evaluate("window.__radarMode = 'error'")
            refresh.click()
            page.wait_for_function(
                "() => document.querySelector('#radarState')?.dataset.state === 'error'",
                timeout=7_500,
            )

            error_text = radar_output.inner_text()
            assert "Radar metadata is unavailable" in error_text
            assert "This does not mean precipitation is absent" in error_text
            assert "DWD RADOLAN observed" not in error_text
            assert "DWD radar nowcast" not in error_text
            assert radar_state.get_attribute("role") == "alert"
            assert radar_state.get_attribute("aria-live") == "assertive"
            assert "controlled radar refresh failure" in radar_state.inner_text()
            assert refresh.is_enabled()
            assert radar_output.get_attribute("aria-busy") == "false"
            assert page.evaluate("window.__radarCalls") == 3

            context.close()
            browser.close()
    finally:
        lab._stop_server(server, thread)
