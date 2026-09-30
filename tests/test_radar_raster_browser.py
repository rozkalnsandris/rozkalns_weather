import importlib.util
from pathlib import Path

import pytest
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
    observed = [
        [0, 0, 1, 0, 0],
        [0, 2, 5, 2, 0],
        [0, 8, 35, 8, 0],
        [0, 2, 5, 2, 0],
        [0, 0, 1, 0, 0],
    ]
    nowcast = [
        [0, 0, 0, 0, 0],
        [0, 0, 3, 0, 0],
        [0, 4, 55, 4, 0],
        [0, 0, 3, 0, 0],
        [0, 0, 0, 0, 0],
    ]
    return {
        "state": "frames_present",
        "frames": [
            {
                "timestamp": "2026-09-28T11:55:00Z",
                "kind": "radar_observed",
                "source": "RADOLAN::RV::observed-fixture",
                "raster": {"width": 5, "height": 5, "values": observed},
            },
            {
                "timestamp": "2026-09-28T12:30:00Z",
                "kind": "radar_nowcast",
                "source": "RADOLAN::RV::nowcast-fixture",
                "raster": {"width": 5, "height": 5, "values": nowcast},
            },
        ],
        "map_contract": {
            "center_location_id": "station_05480",
            "coordinates_exposed": False,
            "geometry_exposed": False,
            "raw_payload_exposed": False,
            "rendering_contract": {
                "state": "raster_ready",
                "raster_rendering_available": True,
                "encoding": "plain_integer_grid",
                "dimensions": {"width": 5, "height": 5},
                "projection": {
                    "id": "DWD_RADOLAN_DE1200",
                    "kind": "polar_stereographic",
                    "pixel_size_m": 1000,
                    "web_mercator_overlay_safe": False,
                },
                "precipitation_unit": {
                    "field": "precipitation_5",
                    "unit": "mm_per_5_min",
                    "scale": 0.01,
                },
                "nodata": {
                    "sentinel": None,
                    "zero_may_include_uncovered_grid_edge": True,
                },
                "crop_radius_m": 20_000,
                "center_marker": "privacy_safe_crop_center",
                "raster_frame_count": 2,
                "timeline_frame_count": 2,
            },
        },
    }


@pytest.mark.parametrize(
    ("viewport", "is_mobile"),
    [
        ({"width": 1440, "height": 900}, False),
        ({"width": 412, "height": 892}, True),
    ],
)
def test_real_shell_renders_privacy_safe_radar_player_without_document_overflow(
    viewport: dict[str, int], is_mobile: bool
) -> None:
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
                viewport=viewport,
                service_workers="block",
                is_mobile=is_mobile,
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            lab._wait_for_forecast(page)

            page.evaluate(
                """payload => {
                  window.__radarCalls = 0;
                  window.apiWithFallback = async (url, key) => {
                    if (url !== '/api/radar' || key !== 'safety-radar') {
                      throw new Error(`unexpected request: ${url} ${key}`);
                    }
                    window.__radarCalls += 1;
                    return {
                      payload,
                      source: 'network',
                      cached_at_utc: '2026-09-28T12:00:00Z',
                      error: null,
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

            canvas = page.locator(".radar-canvas")
            slider = page.locator(".radar-frame-slider")
            badge = page.locator(".radar-kind-badge")
            selected = page.locator(".radar-selected")
            play = page.locator(".radar-play")

            assert canvas.is_visible()
            assert canvas.get_attribute("width") == "5"
            assert canvas.get_attribute("height") == "5"
            assert "Latest observed" in badge.inner_text()
            assert "0.35 mm / 5 min" in selected.inner_text()
            assert slider.get_attribute("aria-label") == "Radar frame timeline"
            assert page.evaluate("window.__radarCalls") == 1
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

            slider.press("ArrowRight")
            assert "Nowcast" in badge.inner_text()
            assert "0.55 mm / 5 min" in selected.inner_text()
            assert "Europe/Berlin" in (canvas.get_attribute("aria-label") or "")

            details = page.locator(".radar-diagnostics")
            details.locator("summary").click()
            technical = details.inner_text()
            assert "DWD_RADOLAN_DE1200" in technical
            assert "web_mercator_overlay_safe" in technical
            assert '"coordinates_exposed": false' in technical
            assert "51.5763" not in technical
            assert "7.8879" not in technical

            if is_mobile:
                box = play.bounding_box()
                assert box is not None and box["height"] >= 44
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

            context.close()
            browser.close()
    finally:
        lab._stop_server(server, thread)
