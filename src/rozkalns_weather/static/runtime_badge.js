function deriveRuntimeBadge({ online = true, readinessOk = false, healthState = "loading", apiUnavailable = false } = {}) {
  if (!online) return "offline";
  if (apiUnavailable) return "API unavailable";
  if (!readinessOk) return "degraded";
  return healthState === "fresh" ? "ready" : "degraded";
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { deriveRuntimeBadge };
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

  window.addEventListener("offline", renderRuntimeBadge);
  window.addEventListener("online", refreshReadiness);
  refreshReadiness();
}
