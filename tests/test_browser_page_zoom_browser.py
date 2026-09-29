import importlib.util
import json
import math
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
LAB_PATH = ROOT / "tests" / "test_ui_performance_lab_browser.py"
TEXT_SCALE_PATH = ROOT / "tests" / "test_ui_text_scale_browser.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_default_browser_zoom(user_data_dir: Path, factor: float) -> None:
    # Chromium stores page zoom as a logarithmic zoom level in the profile's
    # per-partition preference map. The default partition key is "x" because
    # its path relative to the profile root is empty.
    zoom_level = math.log(factor) / math.log(1.2)
    default_dir = user_data_dir / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)
    (default_dir / "Preferences").write_text(
        json.dumps({"partition": {"default_zoom_level": {"x": zoom_level}}}),
        encoding="utf-8",
    )


def test_real_shell_reflows_at_browser_native_200_percent_page_zoom() -> None:
    lab = _load_module(LAB_PATH, "rozkalns_ui_performance_lab")
    text_scale = _load_module(TEXT_SCALE_PATH, "rozkalns_ui_text_scale")
    server, thread = lab._start_server()
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    try:
        with tempfile.TemporaryDirectory(prefix="rozkalns-browser-zoom-") as tmp:
            user_data_dir = Path(tmp)
            _seed_default_browser_zoom(user_data_dir, 2.0)

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

                page.goto(url, wait_until="domcontentloaded", timeout=15_000)
                lab._wait_for_forecast(page)

                metrics = cdp.send("Page.getLayoutMetrics")
                zoom = metrics["cssVisualViewport"]["zoom"]
                assert abs(zoom - 2.0) <= 0.01, metrics["cssVisualViewport"]
                assert page.evaluate("window.innerWidth") < 1440

                for view_id in ("overview", "models", "safety", "accuracy", "status"):
                    text_scale._assert_view_reflows_without_document_overflow(page, view_id)

                context.close()
    finally:
        lab._stop_server(server, thread)
