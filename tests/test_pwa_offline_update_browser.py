from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import mimetypes
import shutil
import threading
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Playwright, expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"
SW = STATIC / "sw.js"


class _ReusableServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], mode: str):
        self.mode = mode
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
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            body = _page(self.server.mode).encode()
            self._write(200, body, "text/html; charset=utf-8")
            return

        if path in {"/sw.js", "/static/sw.js"}:
            source = SW.read_text()
            if self.server.mode == "old":
                source = source.replace('const CACHE = "rozkalns-weather-v32"', 'const CACHE = "rozkalns-weather-v31"')
            self._write(200, source.encode(), "application/javascript; charset=utf-8")
            return

        if path.startswith("/static/"):
            target = STATIC / path.removeprefix("/static/")
            if not target.is_file():
                self._write(404, b"missing", "text/plain; charset=utf-8")
                return
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type in {"application/javascript", "application/manifest+json", "image/svg+xml"}:
                content_type += "; charset=utf-8"
            self._write(200, target.read_bytes(), content_type)
            return

        self._write(404, b"not found", "text/plain; charset=utf-8")


def _page(mode: str) -> str:
    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>PWA lifecycle proof</title></head>
<body>
  <main id="shell-marker">shell-{mode}</main>
  <output id="proof" data-build="{mode}"></output>
  <script>
    // Mirror the production app.js canonical root-scope registration.
    navigator.serviceWorker.register('/sw.js', {{scope:'/'}});
  </script>
  <script src="/static/pwa_lifecycle.js"></script>
  <script>
    (async () => {{
      const proof = document.getElementById('proof');
      try {{
        await navigator.serviceWorker.ready;
        if (!navigator.serviceWorker.controller) {{
          await new Promise((resolve) => {{
            navigator.serviceWorker.addEventListener('controllerchange', resolve, {{ once: true }});
          }});
        }}
        const registrations = await navigator.serviceWorker.getRegistrations();
        proof.dataset.controller = String(Boolean(navigator.serviceWorker.controller));
        proof.dataset.controllerPath = navigator.serviceWorker.controller ? new URL(navigator.serviceWorker.controller.scriptURL).pathname : '';
        proof.dataset.caches = (await caches.keys()).sort().join(',');
        proof.dataset.lifecycle = document.documentElement.dataset.pwaLifecycle || '';
        proof.dataset.registrationScopes = registrations.map((registration) => new URL(registration.scope).pathname).sort().join(',');
        proof.dataset.ready = 'true';
      }} catch (error) {{
        proof.dataset.error = String(error);
        proof.dataset.ready = 'error';
      }}
    }})();
  </script>
</body>
</html>"""


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the PWA lifecycle proof")


def _launch_context(playwright: Playwright, profile: Path) -> BrowserContext:
    return playwright.chromium.launch_persistent_context(
        user_data_dir=profile,
        executable_path=_browser_binary(),
        headless=True,
        args=["--no-sandbox", "--disable-gpu"],
        viewport={"width": 900, "height": 700},
        service_workers="allow",
    )


def _assert_snapshot(
    context: BrowserContext,
    url: str,
    *,
    build: str,
    cache: str,
    lifecycle: str,
) -> None:
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(url, wait_until="load", timeout=15_000)

    proof = page.locator("#proof")
    expect(proof).to_have_attribute("data-ready", "true", timeout=15_000)
    expect(proof).to_have_attribute("data-build", build)
    expect(proof).to_have_attribute("data-controller", "true")
    expect(proof).to_have_attribute("data-controller-path", "/sw.js")
    expect(proof).to_have_attribute("data-registration-scopes", "/")
    expect(proof).to_have_attribute("data-lifecycle", lifecycle)
    expect(proof).to_have_attribute("data-caches", cache)


def _start_server(mode: str, port: int = 0) -> tuple[_ReusableServer, threading.Thread]:
    server = _ReusableServer(("127.0.0.1", port), mode)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_server(server: _ReusableServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_clean_install_offline_reopen_and_atomic_worker_update(tmp_path: Path) -> None:
    profile = tmp_path / "chrome-profile"
    old_server, old_thread = _start_server("old")
    port = old_server.server_address[1]
    url = f"http://127.0.0.1:{port}/"

    with sync_playwright() as playwright:
        try:
            initial_context = _launch_context(playwright, profile)
            try:
                _assert_snapshot(
                    initial_context,
                    url,
                    build="old",
                    cache="rozkalns-weather-v31",
                    lifecycle="ready",
                )
            finally:
                initial_context.close()
        finally:
            _stop_server(old_server, old_thread)

        offline_context = _launch_context(playwright, profile)
        try:
            _assert_snapshot(
                offline_context,
                url,
                build="old",
                cache="rozkalns-weather-v31",
                lifecycle="ready",
            )
        finally:
            offline_context.close()

        new_server, new_thread = _start_server("new", port)
        try:
            updated_context = _launch_context(playwright, profile)
            try:
                _assert_snapshot(
                    updated_context,
                    url,
                    build="new",
                    cache="rozkalns-weather-v32",
                    lifecycle="updated",
                )
            finally:
                updated_context.close()
        finally:
            _stop_server(new_server, new_thread)
