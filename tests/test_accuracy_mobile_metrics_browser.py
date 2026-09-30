import json
import math
from pathlib import Path
import shutil
import tempfile

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
ACCURACY = ROOT / "src" / "rozkalns_weather" / "static" / "accuracy_v3.js"

SUMMARY = {
    "verification_ready": True,
    "truth_quality": {"reason_codes": []},
    "providers": {},
    "common_sample_slices": [
        {
            "provider": "fixture_model",
            "model_version": "fixture-v1",
            "variable": "temperature_2m",
            "lead_bucket": "24-47h",
            "n": 37,
            "missingness": {"missing_n": 2, "expected_n": 39, "common_n": 37},
            "sample_sufficiency_state": "sufficient",
            "mae": 1.23,
            "rmse": 1.56,
            "bias": -0.12,
            "p10_p90_coverage": 0.81,
            "coverage_n": 37,
        }
    ],
}


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the Accuracy mobile proof")


def _seed_default_browser_zoom(user_data_dir: Path, factor: float) -> None:
    zoom_level = math.log(factor) / math.log(1.2)
    default_dir = user_data_dir / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)
    (default_dir / "Preferences").write_text(
        json.dumps({"partition": {"default_zoom_level": {"x": zoom_level}}}),
        encoding="utf-8",
    )


def _render(page) -> None:
    page.set_content(
        """<!doctype html><html><body style="margin:0">
        <main style="max-width:1200px;margin:auto;padding:12px">
          <div id="providerClasses"></div>
          <section class="panel"><div class="panel-title"></div>
            <div id="accuracyTable" class="table-wrap"></div>
          </section>
          <div id="leadBucketTable"></div><div id="calibrationTable"></div>
        </main></body></html>"""
    )
    page.evaluate(
        """summary => {
          window.fetch = async (url) => {
            const value = String(url);
            if (value.includes('/api/providers')) return {ok:true, json:async()=>({providers:[]})};
            if (value.includes('/api/verification/summary')) return {ok:true, json:async()=>summary};
            if (value.includes('/api/verification/precipitation')) return {ok:true, json:async()=>({probability:{}})};
            throw new Error(`unexpected fetch ${value}`);
          };
        }""",
        SUMMARY,
    )
    page.add_script_tag(path=str(ACCURACY))
    page.evaluate("accuracy(30)")
    expect(page.locator("#accuracyTable")).not_to_have_attribute("aria-busy", "true")


def _assert_full_metric_card(page) -> None:
    cards = page.locator("#accuracyTable .accuracy-mobile-cards")
    expect(cards).to_be_visible()
    expect(page.locator("#accuracyTable .accuracy-desktop-table")).to_be_hidden()
    card = page.locator("#accuracyTable .accuracy-metric-card")
    expect(card).to_have_count(1)
    text = card.inner_text()
    for value in (
        "Model", "fixture_model", "Version", "fixture-v1", "Lead", "24-47h",
        "n", "37", "Missing", "2/39", "Sufficiency", "sufficient",
        "MAE", "1.23", "RMSE", "1.56", "Bias", "-0.12", "p10–p90", "81% (37)",
    ):
        assert value in text
    card.focus()
    assert page.evaluate("document.activeElement.classList.contains('accuracy-metric-card')")
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    box = card.bounding_box()
    assert box is not None
    assert box["x"] >= 0
    assert box["x"] + box["width"] <= page.evaluate("document.documentElement.clientWidth") + 1


def test_accuracy_keeps_desktop_table_and_exposes_all_metrics_on_galaxy_a55() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_browser_binary(), headless=True, args=["--no-sandbox", "--disable-gpu"])
        try:
            desktop = browser.new_page(viewport={"width": 1440, "height": 900})
            _render(desktop)
            expect(desktop.locator("#accuracyTable .accuracy-desktop-table")).to_be_visible()
            expect(desktop.locator("#accuracyTable .accuracy-mobile-cards")).to_be_hidden()
            assert "1.23" in desktop.locator("#accuracyTable table").inner_text()
            assert desktop.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")

            mobile = browser.new_page(viewport={"width": 412, "height": 892})
            _render(mobile)
            _assert_full_metric_card(mobile)
        finally:
            browser.close()


def test_accuracy_uses_metric_cards_at_native_200_percent_browser_zoom() -> None:
    with tempfile.TemporaryDirectory(prefix="rozkalns-accuracy-zoom-") as tmp:
        profile = Path(tmp)
        _seed_default_browser_zoom(profile, 2.0)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile),
                executable_path=_browser_binary(),
                headless=True,
                args=["--no-sandbox", "--disable-gpu"],
                viewport={"width": 1440, "height": 900},
                service_workers="block",
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                cdp = context.new_cdp_session(page)
                _render(page)
                zoom = cdp.send("Page.getLayoutMetrics")["cssVisualViewport"]["zoom"]
                assert abs(zoom - 2.0) <= 0.01
                assert page.evaluate("window.innerWidth") <= 760
                _assert_full_metric_card(page)
            finally:
                context.close()
