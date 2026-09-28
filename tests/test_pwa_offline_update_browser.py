from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import mimetypes
import shutil
import subprocess
import threading
from urllib.parse import urlparse


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

        if path == "/static/sw.js":
            source = SW.read_text()
            if self.server.mode == "old":
                source = source.replace('const CACHE = "rozkalns-weather-v25"', 'const CACHE = "rozkalns-weather-v24"')
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
    navigator.serviceWorker.register('/static/sw.js');
  </script>
  <script src="/static/pwa_lifecycle.js"></script>
  <script>
    (async () => {{
      const proof = document.getElementById('proof');
      try {{
        await navigator.serviceWorker.ready;
        for (let index = 0; index < 80 && !navigator.serviceWorker.controller; index += 1) {{
          await new Promise((resolve) => setTimeout(resolve, 25));
        }}
        await new Promise((resolve) => setTimeout(resolve, 150));
        proof.dataset.controller = String(Boolean(navigator.serviceWorker.controller));
        proof.dataset.caches = (await caches.keys()).sort().join(',');
        proof.dataset.lifecycle = document.documentElement.dataset.pwaLifecycle || '';
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


def _run_browser(url: str, profile: Path, *, budget_ms: int = 3500) -> str:
    completed = subprocess.run(
        [
            _browser_binary(),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile}",
            "--window-size=900,700",
            f"--virtual-time-budget={budget_ms}",
            "--dump-dom",
            url,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=35,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed.stdout


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

    try:
        installed = _run_browser(url, profile)
        assert 'data-ready="true"' in installed, installed
        assert 'data-build="old"' in installed, installed
        assert 'data-controller="true"' in installed, installed
        assert "rozkalns-weather-v24" in installed, installed
    finally:
        _stop_server(old_server, old_thread)

    offline = _run_browser(url, profile)
    assert 'data-ready="true"' in offline, offline
    assert 'data-build="old"' in offline, offline
    assert 'data-controller="true"' in offline, offline
    assert "rozkalns-weather-v24" in offline, offline

    new_server, new_thread = _start_server("new", port)
    try:
        updated = _run_browser(url, profile, budget_ms=5500)
        assert 'data-ready="true"' in updated, updated
        assert 'data-build="new"' in updated, updated
        assert 'data-controller="true"' in updated, updated
        assert 'data-lifecycle="updated"' in updated, updated
        assert "rozkalns-weather-v25" in updated, updated
        assert "rozkalns-weather-v24" not in updated, updated
    finally:
        _stop_server(new_server, new_thread)
