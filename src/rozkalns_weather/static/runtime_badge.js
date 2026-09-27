function deriveRuntimeBadge({ online = true, readinessOk = false, healthState = "loading", apiUnavailable = false } = {}) {
  if (!online) return "offline";
  if (apiUnavailable) return "API unavailable";
  if (!readinessOk) return "degraded";
  return healthState === "fresh" ? "ready" : "degraded";
}

function warningEvidence(payload) {
  if (!payload || payload.authority !== "DWD" || payload.official !== true || !Array.isArray(payload.alerts)) return null;
  const alerts = payload.alerts.filter((alert) => alert && typeof alert === "object" && alert.lifecycle !== "expired");
  return {
    state: alerts.length ? "active" : "clear",
    alerts,
    payload,
    retrievedAtUtc: typeof payload.retrieved_at_utc === "string" ? payload.retrieved_at_utc : null,
  };
}

function reduceWarningState(previous = { state: "unknown", evidence: null }, event = {}) {
  const evidence = previous && previous.evidence ? previous.evidence : null;
  if (event.type === "loading") return { state: "loading", evidence };
  if (event.type === "success") {
    const next = warningEvidence(event.payload);
    return next ? { state: next.state, evidence: next } : { state: evidence ? "stale" : "error", evidence };
  }
  if (event.type === "failure") return { state: evidence ? "stale" : "error", evidence };
  return { state: previous && previous.state ? previous.state : "unknown", evidence };
}

function warningSummary(model) {
  const count = model && model.evidence ? model.evidence.alerts.length : 0;
  if (model.state === "loading") return count
    ? `Checking current DWD status · last known ${count} warning${count === 1 ? "" : "s"}`
    : "Checking current DWD warnings…";
  if (model.state === "active") return `${count} DWD warning${count === 1 ? "" : "s"} · current official response`;
  if (model.state === "clear") return "No active warnings · current DWD response";
  if (model.state === "stale") return count
    ? `Last known: ${count} DWD warning${count === 1 ? "" : "s"} · current status unavailable`
    : "Last known: no active warnings · current status unavailable";
  if (model.state === "error") return "Current DWD warning status unavailable";
  return "Official warning status unknown";
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { deriveRuntimeBadge, warningEvidence, reduceWarningState, warningSummary };
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  const badge = document.querySelector("#statusBadge");
  const networkState = document.querySelector("#networkState");
  let readinessOk = false;
  let readinessUnavailable = false;

  function renderRuntimeBadge() {
    if (!badge || !networkState) return;
    const healthState = networkState.dataset.state || "loading";
    const networkMessage = networkState.textContent || "";
    const apiUnavailable = readinessUnavailable || /API unavailable/i.test(networkMessage);
    const label = deriveRuntimeBadge({
      online: navigator.onLine,
      readinessOk,
      healthState,
      apiUnavailable,
    });
    badge.textContent = label;
    badge.dataset.runtimeState = label === "API unavailable" ? "error" : label;
    badge.setAttribute("aria-label", `Application status: ${label}`);
  }

  async function refreshReadiness() {
    if (!navigator.onLine) {
      readinessOk = false;
      readinessUnavailable = false;
      renderRuntimeBadge();
      return;
    }
    try {
      const response = await fetch("/ready", { cache: "no-store" });
      readinessOk = response.ok;
      readinessUnavailable = false;
    } catch (_error) {
      readinessOk = false;
      readinessUnavailable = true;
    }
    renderRuntimeBadge();
  }

  if (networkState) {
    new MutationObserver(renderRuntimeBadge).observe(networkState, {
      attributes: true,
      attributeFilter: ["data-state", "class"],
      childList: true,
      characterData: true,
      subtree: true,
    });
  }

  const WARNING_CACHE_KEY = "rozkalns-weather-warning-evidence-v1";
  let warningModel = { state: "unknown", evidence: null };
  let warningRequest = 0;

  function cachedWarningEvidence() {
    try {
      const payload = JSON.parse(localStorage.getItem(WARNING_CACHE_KEY) || "null");
      return warningEvidence(payload);
    } catch (_error) {
      return null;
    }
  }

  function persistWarningEvidence(model) {
    if (!model.evidence) return;
    try { localStorage.setItem(WARNING_CACHE_KEY, JSON.stringify(model.evidence.payload)); }
    catch (_error) { /* Warning rendering must not depend on storage availability. */ }
  }

  function warningSurfaceState(model) {
    if (model.state === "loading") return "loading";
    if (model.state === "stale") return "stale";
    if (model.state === "error") return "error";
    return "fresh";
  }

  function renderWarnings(model, error = null) {
    const summary = warningSummary(model);
    const overview = document.querySelector("#overviewWarningState");
    const state = document.querySelector("#warningsState");
    const output = document.querySelector("#warningsOutput");
    const surfaceState = warningSurfaceState(model);
    if (overview) {
      overview.textContent = summary;
      overview.dataset.warningState = model.state;
    }
    if (state) {
      state.className = `surface-state state-${surfaceState}`;
      state.dataset.state = surfaceState;
      state.dataset.warningState = model.state;
      state.textContent = `${surfaceState.toUpperCase()} · ${summary}`;
    }
    if (output) {
      if (model.evidence) output.textContent = JSON.stringify(model.evidence.payload, null, 2);
      else if (error) output.textContent = JSON.stringify({ error: String(error.message || error) }, null, 2);
    }
  }

  async function refreshWarnings() {
    const request = ++warningRequest;
    warningModel = reduceWarningState(warningModel, { type: "loading" });
    renderWarnings(warningModel);
    try {
      const response = await fetch("/api/warnings", { cache: "no-store" });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      const payload = await response.json();
      if (request !== warningRequest) return;
      warningModel = reduceWarningState(warningModel, { type: "success", payload });
      persistWarningEvidence(warningModel);
      renderWarnings(warningModel);
    } catch (error) {
      if (request !== warningRequest) return;
      warningModel = reduceWarningState(warningModel, { type: "failure" });
      renderWarnings(warningModel, error);
    }
  }

  function installWarningController() {
    const cached = cachedWarningEvidence();
    if (cached) warningModel = { state: "stale", evidence: cached };
    renderWarnings(warningModel);
    const refreshButton = document.querySelector("#loadWarnings");
    if (refreshButton) {
      refreshButton.textContent = "Refresh DWD warnings";
      refreshButton.onclick = () => { void refreshWarnings(); };
    }
    const overviewButton = document.querySelector("#overviewWarningsButton");
    if (overviewButton) {
      overviewButton.onclick = () => {
        document.querySelector('.tabs button[data-view="safety"]')?.click();
        void refreshWarnings();
      };
    }
    window.addEventListener("online", () => { void refreshWarnings(); });
    window.addEventListener("offline", () => {
      warningModel = reduceWarningState(warningModel, { type: "failure" });
      renderWarnings(warningModel, new Error("offline"));
    });
    void refreshWarnings();
  }

  window.addEventListener("offline", renderRuntimeBadge);
  window.addEventListener("online", refreshReadiness);
  if (document.readyState === "loading") window.addEventListener("DOMContentLoaded", installWarningController, { once: true });
  else installWarningController();
  refreshReadiness();
}