function deriveRuntimeBadge({ online = true, readinessOk = false, healthState = "loading", apiUnavailable = false } = {}) {
  if (!online) return "offline";
  if (apiUnavailable) return "API unavailable";
  if (!readinessOk) return "degraded";
  return healthState === "fresh" ? "ready" : "degraded";
}

function warningEvidence(payload) {
  const validStates = new Set(["alerts_present", "no_active_alerts"]);
  if (
    !payload ||
    payload.authority !== "DWD" ||
    payload.official !== true ||
    payload.kind !== "official_warning" ||
    !validStates.has(payload.state) ||
    !Array.isArray(payload.alerts) ||
    typeof payload.retrieved_at_utc !== "string" ||
    !Number.isFinite(Date.parse(payload.retrieved_at_utc)) ||
    !payload.reference_location ||
    typeof payload.reference_location !== "object"
  ) return null;
  if (payload.state === "no_active_alerts" && payload.alerts.length !== 0) return null;
  if (payload.state === "alerts_present" && payload.alerts.length === 0) return null;
  if (payload.alerts.some((alert) => !alert || typeof alert !== "object" || !["active", "upcoming", "expired"].includes(alert.lifecycle))) return null;
  const alerts = payload.alerts.filter((alert) => alert.lifecycle !== "expired");
  return {
    state: alerts.length ? "active" : "clear",
    alerts,
    payload,
    retrievedAtUtc: payload.retrieved_at_utc,
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

function warningCheckedAge(retrievedAtUtc, nowMs = Date.now()) {
  if (typeof retrievedAtUtc !== "string" || !retrievedAtUtc) return "";
  const checkedMs = Date.parse(retrievedAtUtc);
  if (!Number.isFinite(checkedMs) || !Number.isFinite(nowMs)) return "";
  const minutes = Math.floor(Math.max(0, nowMs - checkedMs) / 60000);
  if (minutes < 1) return "checked just now";
  if (minutes < 60) return `checked ${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `checked ${hours}h ago`;
  return `checked ${Math.floor(hours / 24)}d ago`;
}

function warningDisplayTime(value) {
  if (typeof value !== "string" || !value) return "";
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) return "";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Berlin",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(parsed);
}

function warningReferenceLabel(payload) {
  const reference = payload && payload.reference_location;
  if (!reference || typeof reference !== "object") return "public DWD reference location";
  return reference.label || reference.id || "public DWD reference location";
}

function warningReadableText(model, error = null) {
  if (!model || !model.evidence) {
    if (error) return `DWD warning status unavailable\n${String(error.message || error)}`;
    return warningSummary(model || { state: "unknown", evidence: null });
  }

  const evidence = model.evidence;
  const payload = evidence.payload || {};
  const lines = [
    "DWD official warnings",
    `Reference location: ${warningReferenceLabel(payload)}`,
  ];

  if (model.state === "stale") {
    lines.push("Current DWD status unavailable; showing last known official warning evidence.");
  } else if (model.state === "loading") {
    lines.push("Checking current DWD status; showing last known official warning evidence.");
  }

  if (!evidence.alerts.length) {
    lines.push("No active warnings in the latest valid DWD response.");
  } else {
    evidence.alerts.forEach((alert, index) => {
      const headline = typeof alert.headline === "string" && alert.headline.trim() ? alert.headline.trim() : "DWD warning";
      const severity = typeof alert.severity === "string" && alert.severity.trim() ? alert.severity.trim().toUpperCase() : "UNKNOWN";
      const lifecycle = typeof alert.lifecycle === "string" && alert.lifecycle.trim() ? alert.lifecycle.trim() : "active";
      const starts = warningDisplayTime(alert.effective || alert.onset);
      const ends = warningDisplayTime(alert.expires);
      lines.push("", `${index + 1}. ${headline}`, `Severity: ${severity}`, `Status: ${lifecycle}`);
      if (starts) lines.push(`Starts: ${starts}`);
      if (ends) lines.push(`Ends: ${ends}`);
      if (typeof alert.description === "string" && alert.description.trim()) lines.push(`Details: ${alert.description.trim()}`);
      if (typeof alert.instruction === "string" && alert.instruction.trim()) lines.push(`Instructions: ${alert.instruction.trim()}`);
    });
  }

  const attribution = typeof payload.source_attribution === "string" && payload.source_attribution.trim()
    ? ` · ${payload.source_attribution.trim()}`
    : "";
  lines.push("", `Authority: DWD${attribution}`);
  const checkedAge = warningCheckedAge(evidence.retrievedAtUtc);
  if (checkedAge) lines.push(`Last checked: ${checkedAge}`);
  return lines.join("\n");
}

function createSingleFlight(task) {
  let inFlight = null;
  return (...args) => {
    if (inFlight) return inFlight;
    inFlight = Promise.resolve()
      .then(() => task(...args))
      .finally(() => { inFlight = null; });
    return inFlight;
  };
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    deriveRuntimeBadge,
    warningEvidence,
    reduceWarningState,
    warningSummary,
    warningCheckedAge,
    warningDisplayTime,
    warningReferenceLabel,
    warningReadableText,
    createSingleFlight,
  };
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

  function renderWarningDiagnostics(output, payload) {
    let details = document.querySelector("#warningsDiagnostics");
    if (!details) {
      details = document.createElement("details");
      details.id = "warningsDiagnostics";
      const summary = document.createElement("summary");
      summary.textContent = "Technical warning JSON";
      const raw = document.createElement("pre");
      raw.id = "warningsDiagnosticsJson";
      details.append(summary, raw);
      if (output.parentNode) output.parentNode.insertBefore(details, output.nextSibling);
    }
    const raw = details.querySelector("#warningsDiagnosticsJson");
    if (payload) {
      if (raw) raw.textContent = JSON.stringify(payload, null, 2);
      details.hidden = false;
    } else {
      if (raw) raw.textContent = "";
      details.hidden = true;
      details.open = false;
    }
  }

  function renderWarnings(model, error = null) {
    const baseSummary = warningSummary(model);
    const checkedAge = warningCheckedAge(model && model.evidence ? model.evidence.retrievedAtUtc : null);
    const summary = checkedAge ? `${baseSummary} · ${checkedAge}` : baseSummary;
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
      output.textContent = warningReadableText(model, error);
      renderWarningDiagnostics(output, model.evidence ? model.evidence.payload : null);
    }
  }

  async function runWarningRefresh() {
    warningModel = reduceWarningState(warningModel, { type: "loading" });
    renderWarnings(warningModel);
    try {
      const response = await fetch("/api/warnings", { cache: "no-store" });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      const payload = await response.json();
      warningModel = reduceWarningState(warningModel, { type: "success", payload });
      persistWarningEvidence(warningModel);
      renderWarnings(warningModel);
    } catch (error) {
      warningModel = reduceWarningState(warningModel, { type: "failure" });
      renderWarnings(warningModel, error);
    }
  }

  const refreshWarnings = createSingleFlight(runWarningRefresh);

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
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && navigator.onLine) void refreshWarnings();
    });
    void refreshWarnings();
  }

  window.addEventListener("offline", renderRuntimeBadge);
  window.addEventListener("online", refreshReadiness);
  if (document.readyState === "loading") window.addEventListener("DOMContentLoaded", installWarningController, { once: true });
  else installWarningController();
  refreshReadiness();
}
