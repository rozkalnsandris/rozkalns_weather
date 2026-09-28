from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import mimetypes
import shutil
import threading
import time
from urllib.parse import urlparse

from playwright.sync_api import Playwright, expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"
INDEX = STATIC / "index.html"


def _summary(*, ready: bool) -> dict:
    missing = {
        "common_n": 40,
        "missing_n": 0,
        "expected_n": 40,
        "available_n": 40,
        "excluded_non_common_n": 0,
    }
    rows = [
        {
            "variable": "temperature_2m",
            "lead_bucket": "0-6h",
            "matched_set_id": "cohort-a",
            "provider": "icon_d2",
            "model_version": "icon-a",
            "n": 40,
            "mae": 1.4,
            "rmse": 1.8,
            "bias": 0.2,
            "sample_sufficiency_state": "limited_sample",
            "missingness": missing,
            "coverage_n": 0,
            "p10_p90_coverage": None,
        },
        {
            "variable": "temperature_2m",
            "lead_bucket": "0-6h",
            "matched_set_id": "cohort-a",
            "provider": "ecmwf_ifs",
            "model_version": "ifs-a",
            "n": 40,
            "mae": 1.2,
            "rmse": 1.6,
            "bias": -0.1,
            "sample_sufficiency_state": "limited_sample",
            "missingness": missing,
            "coverage_n": 0,
            "p10_p90_coverage": None,
        },
        {
            "variable": "temperature_2m",
            "lead_bucket": "6-12h",
            "matched_set_id": "cohort-b",
            "provider": "icon_d2",
            "model_version": "icon-b",
            "n": 40,
            "mae": 1.6,
            "rmse": 2.0,
            "bias": 0.3,
            "sample_sufficiency_state": "limited_sample",
            "missingness": missing,
            "coverage_n": 0,
            "p10_p90_coverage": None,
        },
        {
            "variable": "temperature_2m",
            "lead_bucket": "6-12h",
            "matched_set_id": "cohort-b",
            "provider": "ecmwf_ifs",
            "model_version": "ifs-b",
            "n": 40,
            "mae": 1.5,
            "rmse": 1.9,
            "bias": -0.2,
            "sample_sufficiency_state": "limited_sample",
            "missingness": missing,
            "coverage_n": 0,
            "p10_p90_coverage": None,
        },
    ]
    return {
        "verification_ready": ready,
        "variable": "temperature_2m",
        "truth_quality": {
            "reason_codes": [] if ready else ["TEMPERATURE_COVERAGE_INSUFFICIENT"]
        },
        "providers": {},
        "common_sample_slices": rows,
    }


class _ReusableServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int]):
        self.stage = "fresh"
        super().__init__(address, _Handler)


class _Handler(BaseHTTPRequestHandler):
    server: _ReusableServer

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _write(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _json(self, status: int, payload: dict) -> None:
        self._write(
            status,
            json.dumps(payload).encode(),
            "application/json; charset=utf-8",
        )

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._write(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            target = STATIC / path.removeprefix("/static/")
            if not target.is_file():
                self._write(404, b"missing", "text/plain; charset=utf-8")
                return
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type in {
                "application/javascript",
                "application/manifest+json",
                "image/svg+xml",
            }:
                content_type += "; charset=utf-8"
            self._write(200, target.read_bytes(), content_type)
            return

        if path == "/api/providers":
            self._json(200, {"providers": []})
            return
        if path == "/api/verification/summary":
            time.sleep(0.18)
            if self.server.stage == "error":
                self._json(503, {"detail": "controlled verification outage"})
                return
            self._json(200, _summary(ready=self.server.stage == "fresh"))
            return
        if path == "/api/verification/precipitation":
            self._json(200, {"probability": {}, "occurrence_threshold_mm_per_hour": 0.1})
            return

        if path == "/api/health/providers":
            self._json(200, {"providers": []})
            return
        if path == "/api/hourly":
            self._json(200, {"location": {"id": "station_05480"}, "series": []})
            return
        if path == "/api/daily":
            self._json(200, {"location": {"id": "station_05480"}, "days_by_provider": []})
            return
        if path == "/api/current":
            self._json(200, {})
            return
        if path == "/api/warnings":
            self._json(200, {"warnings": []})
            return
        if path == "/api/radar":
            self._json(200, {})
            return

        self._json(200, {})


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the Accuracy state-matrix proof")


def _start_server() -> tuple[_ReusableServer, threading.Thread]:
    server = _ReusableServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_server(server: _ReusableServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _launch(playwright: Playwright):
    return playwright.chromium.launch(
        executable_path=_browser_binary(),
        headless=True,
        args=["--no-sandbox", "--disable-gpu"],
    )


def test_real_shell_accuracy_filter_tracks_loading_preliminary_and_error_states() -> None:
    server, thread = _start_server()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    try:
        with sync_playwright() as playwright:
            browser = _launch(playwright)
            try:
                page = browser.new_page(viewport={"width": 412, "height": 892})
                page.goto(url, wait_until="load", timeout=15_000)
                page.locator('[data-view="accuracy"]').click()

                server.stage = "fresh"
                page.evaluate("() => { window.accuracy(30); }")
                expect(page.locator("#accuracyState")).to_contain_text("LOADING · 30-day", timeout=2_000)
                expect(page.locator("#accuracyState")).to_have_class("surface-state state-fresh", timeout=5_000)
                cohort = page.locator("#accuracyCohort")
                expect(cohort.locator("option")).to_have_count(2)
                expect(cohort).to_be_enabled()
                cohort.select_option("1")
                expect(page.locator("#accuracySummaryMeta")).to_contain_text("6-12h")
                expect(page.locator("#accuracySummaryRows")).to_contain_text("1.60 °C")

                server.stage = "stale"
                page.evaluate("() => { window.accuracy(90); }")
                expect(page.locator("#accuracyState")).to_contain_text("LOADING · 90-day", timeout=2_000)
                expect(page.locator("#accuracyState")).to_have_class("surface-state state-stale", timeout=5_000)
                expect(cohort.locator("option")).to_have_count(2)
                expect(cohort).to_be_enabled()
                cohort.select_option("1")
                expect(page.locator("#accuracySummaryMeta")).to_contain_text("6-12h")
                expect(page.locator("#leadBucketTable")).to_contain_text(
                    "Lead-bucket aggregates are hidden until verification_ready=true."
                )

                server.stage = "error"
                page.evaluate("() => { window.accuracy(30); }")
                expect(page.locator("#accuracyState")).to_contain_text("LOADING · 30-day", timeout=2_000)
                expect(page.locator("#accuracyState")).to_have_class("surface-state state-error", timeout=5_000)
                expect(page.locator("#accuracyTable")).to_have_text("Accuracy evidence unavailable.")
                expect(page.locator("#accuracySummaryRows")).to_have_text("Common-sample MAE summary unavailable.")
                expect(cohort).to_be_disabled()
                expect(cohort.locator("option")).to_have_count(0)
                expect(page.locator("#accuracySummaryMeta")).to_have_text(
                    "Common-sample cohort metadata unavailable."
                )
                expect(page.locator("#accuracyWeatherNextReadiness")).to_have_text(
                    "WeatherNext 3 accuracy is unavailable until verification evidence can be loaded."
                )
            finally:
                browser.close()
    finally:
        _stop_server(server, thread)
