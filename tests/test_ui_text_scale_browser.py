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


def _assert_view_reflows_without_document_overflow(page, view_id: str) -> None:
    page.locator(f'button[data-view="{view_id}"]').click()
    page.wait_for_function(
        "viewId => document.getElementById(viewId)?.classList.contains('active')",
        view_id,
    )
    overflow = page.evaluate(
        """() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
          innerWidth: window.innerWidth,
          activeView: document.querySelector('.view.active')?.id || null,
        })"""
    )
    assert overflow["activeView"] == view_id, overflow
    assert overflow["scrollWidth"] <= overflow["clientWidth"] + 1, overflow

    nav = page.locator(".bottom-nav")
    nav_box = nav.bounding_box()
    assert nav_box is not None
    assert nav_box["x"] >= -1, nav_box
    assert nav_box["x"] + nav_box["width"] <= overflow["innerWidth"] + 1, (nav_box, overflow)

    for button in page.locator(".bottom-nav button").all():
        dimensions = button.evaluate(
            "el => ({clientWidth: el.clientWidth, scrollWidth: el.scrollWidth, clientHeight: el.clientHeight, scrollHeight: el.scrollHeight})"
        )
        assert dimensions["scrollWidth"] <= dimensions["clientWidth"] + 1, dimensions
        assert dimensions["scrollHeight"] <= dimensions["clientHeight"] + 1, dimensions


def test_real_shell_reflows_at_200_percent_os_text_scale() -> None:
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
            cdp = context.new_cdp_session(page)
            cdp.send("Emulation.setEmulatedOSTextScale", {"scale": 2.0})

            page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            lab._wait_for_forecast(page)

            for view_id in ("overview", "models", "safety", "accuracy", "status"):
                _assert_view_reflows_without_document_overflow(page, view_id)

            context.close()
            browser.close()
    finally:
        lab._stop_server(server, thread)
