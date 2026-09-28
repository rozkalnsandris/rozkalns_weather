import importlib.util
import json
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


def test_emit_full_layout_shift_sources() -> None:
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
            )
            page = context.new_page()
            page.add_init_script(
                r"""
                (() => {
                  const rect = (value) => value ? {
                    x: value.x,
                    y: value.y,
                    width: value.width,
                    height: value.height,
                  } : null;
                  const nodeInfo = (node) => {
                    if (!node) return null;
                    const selectorParts = [];
                    let cursor = node;
                    for (let depth = 0; cursor && cursor.nodeType === 1 && depth < 6; depth += 1) {
                      const tag = String(cursor.tagName || 'node').toLowerCase();
                      if (cursor.id) {
                        selectorParts.unshift(`#${cursor.id}`);
                        break;
                      }
                      const classes = Array.from(cursor.classList || []).slice(0, 4);
                      let part = `${tag}${classes.length ? `.${classes.join('.')}` : ''}`;
                      if (cursor.parentElement) {
                        const siblings = Array.from(cursor.parentElement.children).filter(
                          (child) => child.tagName === cursor.tagName
                        );
                        if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(cursor) + 1})`;
                      }
                      selectorParts.unshift(part);
                      cursor = cursor.parentElement;
                    }
                    const parent = node.parentElement;
                    return {
                      selector: selectorParts.join(' > '),
                      tag: String(node.tagName || node.nodeName || 'node').toLowerCase(),
                      id: node.id || null,
                      classes: Array.from(node.classList || []),
                      parent: parent ? {
                        tag: String(parent.tagName || 'node').toLowerCase(),
                        id: parent.id || null,
                        classes: Array.from(parent.classList || []),
                      } : null,
                      text: String(node.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 240),
                      html: String(node.outerHTML || '').replace(/\s+/g, ' ').slice(0, 600),
                    };
                  };
                  const supported = (PerformanceObserver.supportedEntryTypes || []).includes('layout-shift');
                  window.__rozkalnsClsDiagnostic = {supported, cls: 0, shifts: []};
                  if (!supported) return;
                  new PerformanceObserver((list) => {
                    for (const entry of list.getEntries()) {
                      if (entry.hadRecentInput) continue;
                      window.__rozkalnsClsDiagnostic.cls += entry.value || 0;
                      window.__rozkalnsClsDiagnostic.shifts.push({
                        value: entry.value || 0,
                        startTime: entry.startTime || 0,
                        sources: (entry.sources || []).map((source) => ({
                          node: nodeInfo(source.node),
                          previousRect: rect(source.previousRect),
                          currentRect: rect(source.currentRect),
                        })),
                      });
                    }
                  }).observe({type: 'layout-shift', buffered: true});
                })();
                """
            )

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
            lab._wait_for_forecast(page)
            page.locator("#refreshOverview").click()
            page.wait_for_timeout(250)
            diagnostic = page.evaluate("window.__rozkalnsClsDiagnostic")

            print("CLS_DIAGNOSTIC_BEGIN")
            print(
                "CLS_DIAGNOSTIC_SUMMARY="
                + json.dumps(
                    {
                        "supported": diagnostic["supported"],
                        "cls": diagnostic["cls"],
                        "shift_count": len(diagnostic["shifts"]),
                    },
                    sort_keys=True,
                )
            )
            for index, shift in enumerate(diagnostic["shifts"]):
                print(f"CLS_SHIFT_{index}=" + json.dumps(shift, sort_keys=True))
            print("CLS_DIAGNOSTIC_END")

            assert diagnostic["supported"], diagnostic
            assert diagnostic["cls"] <= 0.1, (
                f"diagnostic reproduction: CLS={diagnostic['cls']:.12f}; "
                "see CLS_SHIFT_* captured stdout for complete source attribution"
            )

            context.close()
            browser.close()
    finally:
        lab._stop_server(server, thread)
