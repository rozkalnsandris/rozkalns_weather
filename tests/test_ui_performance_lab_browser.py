from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import mimetypes
import shutil
import threading
import time
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"


class _LabServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int]):
        self.api_mode = "ok"
        self.api_delay_seconds = 0.08
        super().__init__(address, _Handler)


class _Handler(BaseHTTPRequestHandler):
    server: _LabServer

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _write(self, status: int, body: bytes, content_type: str, *, cache_control: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            self._api(path, parse_qs(parsed.query))
            return

        if path == "/":
            self._write(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            return

        if path == "/sw.js":
            self._write(200, (STATIC / "sw.js").read_bytes(), "application/javascript; charset=utf-8")
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
            self._write(200, target.read_bytes(), content_type, cache_control="public, max-age=3600")
            return

        self._write(404, b"not found", "text/plain; charset=utf-8")

    def _api(self, path: str, query: dict[str, list[str]]) -> None:
        time.sleep(self.server.api_delay_seconds)
        if self.server.api_mode == "fail":
            self._write(503, b'{"detail":"controlled lab failure"}', "application/json")
            return

        now = datetime.now(timezone.utc).replace(microsecond=0)
        payload = _api_payload(path, query, now)
        self._write(200, json.dumps(payload).encode(), "application/json")


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _provider(provider_id: str, model_name: str, now: datetime) -> dict[str, object]:
    return {
        "id": provider_id,
        "model_name": model_name,
        "state": "success",
        "ingest_state": "success",
        "freshness_state": "fresh",
        "last_retrieved_at_utc": _iso(now - timedelta(minutes=5)),
    }


def _api_payload(path: str, query: dict[str, list[str]], now: datetime) -> dict[str, object]:
    if path == "/api/health/providers":
        return {
            "home": {"configured": False},
            "providers": [
                _provider("dwd_observations", "DWD CDC observations", now),
                _provider("icon_d2", "ICON-D2", now),
                _provider("ecmwf_ifs", "ECMWF IFS", now),
                _provider("ecmwf_aifs", "ECMWF AIFS", now),
                {
                    "id": "weathernext3",
                    "model_name": "WeatherNext 3",
                    "state": "access_pending",
                    "ingest_state": "access_pending",
                    "freshness_state": "not_ingested",
                },
            ],
        }

    if path == "/api/current":
        observed = _iso(now - timedelta(minutes=10))
        values = {
            "temperature_2m": 13.2,
            "relative_humidity_2m": 72.0,
            "wind_speed_10m": 4.1,
            "pressure_msl": 1015.0,
            "precipitation_1h": 0.0,
            "cloud_cover": 52.0,
            "wind_gust_10m": 7.5,
        }
        return {
            "location": {"id": "station_05480", "label": "Werl"},
            "truth_source": "DWD CDC 05480",
            "observations": [
                {"variable": variable, "value": value, "observed_at_utc": observed}
                for variable, value in values.items()
            ],
        }

    if path == "/api/hourly":
        location_id = query.get("location_id", ["station_05480"])[0]
        variable = query.get("variable", ["temperature_2m"])[0]
        init = now.replace(minute=0, second=0)
        rows = []
        for hour in range(1, 9):
            valid = init + timedelta(hours=hour)
            if variable == "temperature_2m":
                value = 12.0 + hour * 0.35
            elif variable == "precipitation_1h":
                value = 0.2 if hour in {3, 4} else 0.0
            elif variable == "wind_speed_10m":
                value = 4.0 + hour * 0.1
            else:
                value = 0.0
            rows.append(
                {
                    "provider": "icon_d2",
                    "model_name": "ICON-D2",
                    "model_version": "lab-fixture",
                    "statistic": "deterministic",
                    "value": value,
                    "init_time_utc": _iso(init),
                    "valid_time_utc": _iso(valid),
                    "retrieved_at_utc": _iso(now - timedelta(minutes=5)),
                    "lead_hours": hour,
                }
            )
        return {"location": {"id": location_id}, "series": rows}

    if path == "/api/daily":
        location_id = query.get("location_id", ["station_05480"])[0]
        today = now.date()
        rows = []
        for offset in range(5):
            rows.append(
                {
                    "provider": "icon_d2",
                    "model_name": "ICON-D2",
                    "date": (today + timedelta(days=offset)).isoformat(),
                    "temperature_min_c": 7.0 + offset,
                    "temperature_max_c": 14.0 + offset,
                    "precipitation_sum_mm": 0.5 if offset == 2 else 0.0,
                    "retrieved_at_utc": _iso(now - timedelta(minutes=5)),
                }
            )
        return {"location": {"id": location_id}, "days_by_provider": rows}

    if path == "/api/warnings":
        return {"state": "no_active_alerts", "alerts": []}

    if path == "/api/readiness":
        return {"status": "ready", "ready": True}

    return {}


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the UI performance lab")


def _start_server() -> tuple[_LabServer, threading.Thread]:
    server = _LabServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_server(server: _LabServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _install_metric_observers(page) -> None:
    page.add_init_script(
        """
        (() => {
          window.__rozkalnsPerf = {lcp: 0, cls: 0, maxEventDuration: 0, supported: {}};
          const supported = PerformanceObserver.supportedEntryTypes || [];
          window.__rozkalnsPerf.supported.lcp = supported.includes('largest-contentful-paint');
          window.__rozkalnsPerf.supported.cls = supported.includes('layout-shift');
          window.__rozkalnsPerf.supported.event = supported.includes('event');
          if (window.__rozkalnsPerf.supported.lcp) {
            new PerformanceObserver((list) => {
              for (const entry of list.getEntries()) window.__rozkalnsPerf.lcp = Math.max(window.__rozkalnsPerf.lcp, entry.startTime || 0);
            }).observe({type: 'largest-contentful-paint', buffered: true});
          }
          if (window.__rozkalnsPerf.supported.cls) {
            new PerformanceObserver((list) => {
              for (const entry of list.getEntries()) if (!entry.hadRecentInput) window.__rozkalnsPerf.cls += entry.value || 0;
            }).observe({type: 'layout-shift', buffered: true});
          }
          if (window.__rozkalnsPerf.supported.event) {
            new PerformanceObserver((list) => {
              for (const entry of list.getEntries()) window.__rozkalnsPerf.maxEventDuration = Math.max(window.__rozkalnsPerf.maxEventDuration, entry.duration || 0);
            }).observe({type: 'event', buffered: true, durationThreshold: 16});
          }
        })();
        """
    )


def _wait_for_forecast(page, timeout_ms: int = 7_500) -> float:
    page.wait_for_selector("#hourlyStrip .hour-card", timeout=timeout_ms)
    page.wait_for_function(
        "() => ['fresh','stale','offline'].includes(document.querySelector('#overviewTempState')?.dataset.state)",
        timeout=timeout_ms,
    )
    return float(page.evaluate("performance.now()"))


def test_controlled_mobile_performance_lab_and_cached_failure_fallback() -> None:
    server, thread = _start_server()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=_browser_binary(),
                headless=True,
                args=["--no-sandbox", "--disable-gpu"],
            )
            context = browser.new_context(
                viewport={"width": 412, "height": 892},
                service_workers="block",
            )
            page = context.new_page()
            _install_metric_observers(page)

            cdp = context.new_cdp_session(page)
            cdp.send("Network.enable")
            cdp.send(
                "Network.emulateNetworkConditions",
                {
                    "offline": False,
                    "latency": 100,
                    "downloadThroughput": 200_000,
                    "uploadThroughput": 75_000,
                    "connectionType": "cellular3g",
                },
            )

            page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            cold_ttff_ms = _wait_for_forecast(page)
            page.locator("#refreshOverview").click()
            page.wait_for_timeout(250)
            cold_metrics = page.evaluate("window.__rozkalnsPerf")

            assert cold_ttff_ms <= 3_500, f"controlled cold TTFF regression: {cold_ttff_ms:.1f} ms"
            assert cold_metrics["cls"] <= 0.1, cold_metrics
            if cold_metrics["supported"]["lcp"]:
                assert 0 < cold_metrics["lcp"] <= 4_000, cold_metrics
            if cold_metrics["supported"]["event"]:
                assert cold_metrics["maxEventDuration"] <= 200, cold_metrics

            cdp.send(
                "Network.emulateNetworkConditions",
                {
                    "offline": False,
                    "latency": 0,
                    "downloadThroughput": -1,
                    "uploadThroughput": -1,
                    "connectionType": "none",
                },
            )
            server.api_delay_seconds = 0.02
            page.reload(wait_until="domcontentloaded", timeout=15_000)
            warm_ttff_ms = _wait_for_forecast(page)
            assert warm_ttff_ms <= 2_000, f"controlled warm TTFF regression: {warm_ttff_ms:.1f} ms"

            server.api_mode = "fail"
            server.api_delay_seconds = 0
            page.reload(wait_until="domcontentloaded", timeout=15_000)
            cached_failure_ttff_ms = _wait_for_forecast(page)
            cached_state = page.locator("#overviewTempState").get_attribute("data-state")
            assert cached_failure_ttff_ms <= 2_000, (
                f"cached failure TTFF regression: {cached_failure_ttff_ms:.1f} ms"
            )
            assert cached_state == "stale"
            assert "not current" in page.locator("#overviewTempState").inner_text().lower()

            context.close()
            browser.close()
    finally:
        _stop_server(server, thread)
