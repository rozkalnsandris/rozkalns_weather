import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from playwright.sync_api import Route, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
LAB_PATH = ROOT / "tests" / "test_ui_performance_lab_browser.py"
ZOOM_PATH = ROOT / "tests" / "test_browser_page_zoom_browser.py"
LONG_REASON = "NOT_IN_PUBLIC_RECURRING_SCOPE"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _install_long_reason_route(page, lab) -> None:
    def provider_health(route: Route) -> None:
        payload = lab._api_payload(
            "/api/health/providers",
            {},
            datetime.now(timezone.utc).replace(microsecond=0),
        )
        weather_next = next(
            provider for provider in payload["providers"] if provider["id"] == "weathernext3"
        )
        weather_next.update(
            {
                "state": "access_pending",
                "ingest_state": "access_pending",
                "freshness_state": "not_tracked",
                "reason_code": LONG_REASON,
            }
        )
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        )

    page.route("**/api/health/providers", provider_health)


def _assert_long_provider_token_wraps(page, url: str, lab) -> None:
    _install_long_reason_route(page, lab)
    page.goto(url, wait_until="domcontentloaded", timeout=15_000)
    lab._wait_for_forecast(page)
    page.locator('button[data-view="models"]').click()
    page.wait_for_function(
        f"() => document.querySelector('#providerClasses')?.textContent.includes('{LONG_REASON}')",
        timeout=7_500,
    )

    card = page.locator("#providerClasses .provider").filter(has_text=LONG_REASON)
    assert card.count() == 1
    detail = card.locator("small")
    assert LONG_REASON in detail.inner_text()

    card_metrics = card.evaluate(
        """node => {
          const rect = node.getBoundingClientRect();
          const parent = node.parentElement.getBoundingClientRect();
          return {
            clientWidth: node.clientWidth,
            scrollWidth: node.scrollWidth,
            left: rect.left,
            right: rect.right,
            parentLeft: parent.left,
            parentRight: parent.right,
          };
        }"""
    )
    detail_metrics = detail.evaluate(
        "node => ({clientWidth: node.clientWidth, scrollWidth: node.scrollWidth})"
    )

    assert card_metrics["scrollWidth"] <= card_metrics["clientWidth"] + 1, card_metrics
    assert detail_metrics["scrollWidth"] <= detail_metrics["clientWidth"] + 1, detail_metrics
    assert card_metrics["left"] >= card_metrics["parentLeft"] - 1, card_metrics
    assert card_metrics["right"] <= card_metrics["parentRight"] + 1, card_metrics
    assert page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
    )


def test_models_provider_reason_code_wraps_on_desktop_and_galaxy_a55() -> None:
    lab = _load_module(LAB_PATH, "rozkalns_ui_provider_wrap_lab")
    server, thread = lab._start_server()
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=lab._browser_binary(),
                headless=True,
                args=["--no-sandbox", "--disable-gpu"],
            )
            for viewport, is_mobile in (
                ({"width": 1440, "height": 900}, False),
                ({"width": 412, "height": 892}, True),
            ):
                context = browser.new_context(
                    viewport=viewport,
                    service_workers="block",
                    is_mobile=is_mobile,
                )
                page = context.new_page()
                _assert_long_provider_token_wraps(page, url, lab)
                context.close()
            browser.close()
    finally:
        lab._stop_server(server, thread)


def test_models_provider_reason_code_wraps_at_native_200_percent_page_zoom() -> None:
    lab = _load_module(LAB_PATH, "rozkalns_ui_provider_wrap_zoom_lab")
    zoom = _load_module(ZOOM_PATH, "rozkalns_ui_provider_wrap_zoom")
    server, thread = lab._start_server()
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    try:
        with tempfile.TemporaryDirectory(prefix="rozkalns-provider-wrap-zoom-") as tmp:
            user_data_dir = Path(tmp)
            zoom._seed_default_browser_zoom(user_data_dir, 2.0)

            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    str(user_data_dir),
                    executable_path=lab._browser_binary(),
                    headless=True,
                    args=["--no-sandbox", "--disable-gpu"],
                    viewport={"width": 1440, "height": 900},
                    service_workers="block",
                )
                page = context.pages[0] if context.pages else context.new_page()
                cdp = context.new_cdp_session(page)
                _assert_long_provider_token_wraps(page, url, lab)

                metrics = cdp.send("Page.getLayoutMetrics")
                assert abs(metrics["cssVisualViewport"]["zoom"] - 2.0) <= 0.01
                context.close()
    finally:
        lab._stop_server(server, thread)
