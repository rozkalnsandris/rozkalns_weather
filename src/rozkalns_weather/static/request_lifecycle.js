(() => {
  "use strict";

  const DATA_CACHE_PREFIX = "rozkalns-weather:pwa-cache:v1:";
  const DEFAULT_TIMEOUT_MS = 10_000;

  function storageRead(key) {
    try {
      const raw = localStorage.getItem(`${DATA_CACHE_PREFIX}${key}`);
      if (!raw) return null;
      const value = JSON.parse(raw);
      if (!value || typeof value !== "object" || !value.payload || !value.cached_at_utc) return null;
      return value;
    } catch (_error) {
      return null;
    }
  }

  function storageWrite(key, payload) {
    const value = { cached_at_utc: new Date().toISOString(), payload };
    try { localStorage.setItem(`${DATA_CACHE_PREFIX}${key}`, JSON.stringify(value)); }
    catch (_error) { /* Cache failure must never block live rendering. */ }
    return value.cached_at_utc;
  }

  function timeoutValue(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) && numeric > 0 ? numeric : DEFAULT_TIMEOUT_MS;
  }

  async function apiWithTimeoutFallback(url, cacheKey, options = {}) {
    const timeoutMs = timeoutValue(options.timeoutMs);
    const externalSignal = options.signal || null;
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    let timer = null;
    let timedOut = false;
    let externalAbortHandler = null;

    if (controller && externalSignal) {
      if (externalSignal.aborted) {
        controller.abort(externalSignal.reason);
      } else {
        externalAbortHandler = () => controller.abort(externalSignal.reason);
        externalSignal.addEventListener("abort", externalAbortHandler, { once: true });
      }
    }

    if (controller) {
      timer = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, timeoutMs);
    }

    try {
      const fetchOptions = { cache: "no-store" };
      if (controller) fetchOptions.signal = controller.signal;
      else if (externalSignal) fetchOptions.signal = externalSignal;
      const response = await fetch(url, fetchOptions);
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      const payload = await response.json();
      return { payload, source: "network", cached_at_utc: storageWrite(cacheKey, payload), error: null };
    } catch (error) {
      const effectiveError = timedOut ? new Error(`Request timed out after ${timeoutMs} ms`) : error;
      const cached = storageRead(cacheKey);
      if (!cached) throw effectiveError;
      return {
        payload: cached.payload,
        source: navigator.onLine ? "stale-cache" : "offline-cache",
        cached_at_utc: cached.cached_at_utc,
        error: String(effectiveError),
      };
    } finally {
      if (timer) clearTimeout(timer);
      if (externalSignal && externalAbortHandler) {
        externalSignal.removeEventListener("abort", externalAbortHandler);
      }
    }
  }

  window.RozkalnsRequestLifecycle = Object.freeze({
    DEFAULT_TIMEOUT_MS,
    apiWithTimeoutFallback,
  });
})();
