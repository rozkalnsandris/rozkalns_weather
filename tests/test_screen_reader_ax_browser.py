import importlib.util
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
LAB_PATH = ROOT / "tests" / "test_ui_performance_lab_browser.py"


def _load_lab_module():
    spec = importlib.util.spec_from_file_location("rozkalns_ui_performance_lab", LAB_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ax_value(node: dict, key: str):
    value = node.get(key)
    return value.get("value") if isinstance(value, dict) else None


def _ax_property(node: dict, name: str):
    for prop in node.get("properties", []):
        if prop.get("name") == name:
            value = prop.get("value")
            return value.get("value") if isinstance(value, dict) else None
    return None


def _nodes_with_role(nodes: list[dict], role: str) -> list[dict]:
    return [
        node
        for node in nodes
        if not node.get("ignored", False) and _ax_value(node, "role") == role
    ]


def test_real_shell_exposes_landmarks_live_regions_and_assertive_failure_to_ax_tree() -> None:
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
            page.route("**/static/radar_timeline.js", lambda route: route.abort())
            cdp = context.new_cdp_session(page)
            cdp.send("Accessibility.enable")

            page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            lab._wait_for_forecast(page)

            baseline = cdp.send("Accessibility.getFullAXTree")["nodes"]
            assert _nodes_with_role(baseline, "main"), "main landmark missing from AX tree"

            navigations = _nodes_with_role(baseline, "navigation")
            assert any(_ax_value(node, "name") == "Primary views" for node in navigations), navigations

            button_names = {
                _ax_value(node, "name")
                for node in _nodes_with_role(baseline, "button")
            }
            assert {"Overview", "Models", "Radar", "Accuracy", "Status"}.issubset(button_names), button_names

            statuses = _nodes_with_role(baseline, "status")
            assert statuses, "status live regions missing from AX tree"
            assert any(_ax_property(node, "live") == "polite" for node in statuses), statuses
            assert any(_ax_property(node, "atomic") is True for node in statuses), statuses

            page.locator('button[data-view="models"]').click()
            page.wait_for_function("() => document.querySelector('#models')?.classList.contains('active')")
            assert page.evaluate("() => document.activeElement?.textContent?.trim()") == "Models"

            page.locator('button[data-view="safety"]').click()
            expect(page.locator("#radarState")).to_have_attribute("role", "alert", timeout=5_000)
            expect(page.locator("#radarState")).to_have_attribute("aria-live", "assertive")
            expect(page.locator("#radarState")).to_contain_text("Radar timeline module could not be loaded")

            failure_tree = cdp.send("Accessibility.getFullAXTree")["nodes"]
            alerts = _nodes_with_role(failure_tree, "alert")
            assert alerts, "assertive radar failure missing from AX tree"
            assert any(_ax_property(node, "live") == "assertive" for node in alerts), alerts
            assert any(_ax_property(node, "atomic") is True for node in alerts), alerts

            cdp.send("Accessibility.disable")
            context.close()
            browser.close()
    finally:
        lab._stop_server(server, thread)
