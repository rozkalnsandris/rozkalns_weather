(() => {
  "use strict";

  const OBSERVATION_FRESH_MINUTES = 180;
  const TICK_MS = 60 * 1000;
  const CURRENT_BOOTSTRAP_DELAY_MS = 200;
  const OBSERVATION_SCRIPT_URL = document.currentScript?.src || "";
  let timer = null;
  let latestResult = null;
  let currentBootstrapTimer = null;
  let currentBootstrapSequence = 0;

  function latestObservationTime(result) {
    return (result?.payload?.observations || [])
      .map((item) => item.observed_at_utc)
      .filter(Boolean)
      .sort()
      .at(-1) || null;
  }

  function parseTimestamp(value) {
    const stamp = new Date(value).getTime();
    return Number.isFinite(stamp) ? stamp : null;
  }

  function localTime(value) {
    const stamp = parseTimestamp(value);
    if (stamp == null) return "—";
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Berlin",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(stamp));
  }

  function ageParts(observed, nowMs = Date.now()) {
    const stamp = parseTimestamp(observed);
    if (stamp == null || !Number.isFinite(nowMs)) return null;
    const minutes = Math.max(0, Math.floor((nowMs - stamp) / 60000));
    return { minutes, hours: Math.floor(minutes / 60), remainderMinutes: minutes % 60 };
  }

  function ageLabel(age) {
    if (!age) return "age unknown";
    if (age.minutes < 1) return "just now";
    if (age.minutes < 60) return `${age.minutes} min ago`;
    return `${age.hours} h ${age.remainderMinutes} min ago`;
  }

  function staleLabel(age) {
    if (!age) return "age unknown";
    if (age.minutes < 60) return `${age.minutes} min old`;
    return `${age.hours} h ${age.remainderMinutes} min old`;
  }

  function updateObservationAge(result = latestResult, nowMs = Date.now()) {
    if (!result) return false;
    const observed = latestObservationTime(result);
    const age = ageParts(observed, nowMs);
    if (!observed || !age) return false;

    const state = document.querySelector("#currentState");
    const heroUpdated = document.querySelector("#heroUpdated");
    if (!state || !heroUpdated) return false;

    if (state.dataset.state === "fresh") {
      delete state.dataset.observationAgeManagedStale;
      if (age.minutes > OBSERVATION_FRESH_MINUTES) {
        const message = `Latest DWD observation ${localTime(observed)} is ${staleLabel(age)}; no newer observation has arrived.`;
        if (typeof window.setSurfaceState === "function") {
          window.setSurfaceState("currentState", "stale", message);
        } else {
          state.hidden = false;
          state.removeAttribute("aria-hidden");
          state.classList.remove("state-fresh");
          state.classList.add("state-stale");
          state.dataset.state = "stale";
          state.setAttribute("role", "status");
          state.setAttribute("aria-live", "polite");
          state.setAttribute("aria-atomic", "true");
          state.textContent = `STALE · ${message}`;
        }
        state.dataset.observationAgeManagedStale = "true";
        heroUpdated.textContent = `Latest observation ${localTime(observed)} · ${staleLabel(age)}`;
        return true;
      }
      heroUpdated.textContent = `Observed ${localTime(observed)} · ${ageLabel(age)}`;
      return true;
    }

    if (state.dataset.state === "stale" && state.dataset.observationAgeManagedStale === "true") {
      const message = `Latest DWD observation ${localTime(observed)} is ${staleLabel(age)}; no newer observation has arrived.`;
      state.textContent = `STALE · ${message}`;
      heroUpdated.textContent = `Latest observation ${localTime(observed)} · ${staleLabel(age)}`;
      return true;
    }

    return false;
  }

  function startObservationAgeTicker(result) {
    latestResult = result || null;
    if (timer) clearInterval(timer);
    timer = null;
    if (!latestObservationTime(latestResult)) return;
    updateObservationAge(latestResult);
    timer = setInterval(() => updateObservationAge(latestResult), TICK_MS);
  }

  function currentStateIsLoading() {
    return document.querySelector("#currentState")?.dataset.state === "loading";
  }

  function clearUnavailableObservationEvidence() {
    const values = {
      heroUpdated: "Current observation unavailable",
      heroTemperature: "—°",
      heroCondition: "Observation unavailable",
      heroIcon: "◌",
      heroFeels: "No current DWD observation available",
      heroSource: "DWD current observation unavailable",
    };
    Object.entries(values).forEach(([id, value]) => {
      const element = document.querySelector(`#${id}`);
      if (element) element.textContent = value;
    });
    ["detailHumidity", "detailWind", "detailPressure", "detailRain", "detailCloud", "detailGust"].forEach((id) => {
      const element = document.querySelector(`#${id}`);
      if (element) element.textContent = "—";
    });
  }

  function currentStateRequiresUnavailableCleanup(state) {
    if (!state) return false;
    return state.dataset.state === "error"
      || String(state.textContent || "").includes("DWD current observation unavailable");
  }

  function installCurrentStateCleanupObserver() {
    const state = document.querySelector("#currentState");
    if (!state || typeof MutationObserver !== "function") return false;
    const synchronize = () => {
      if (currentStateRequiresUnavailableCleanup(state)) clearUnavailableObservationEvidence();
    };
    const observer = new MutationObserver(synchronize);
    observer.observe(state, { attributes: true, childList: true, characterData: true, subtree: true, attributeFilter: ["data-state"] });
    synchronize();
    return true;
  }

  function markCurrentUnavailable(error) {
    const state = document.querySelector("#currentState");
    if (!state || state.dataset.state !== "loading") return;
    clearUnavailableObservationEvidence();
    if (typeof window.setSurfaceState === "function") {
      window.setSurfaceState(
        "currentState",
        navigator.onLine ? "error" : "offline",
        `DWD current observation unavailable: ${error}`,
        { alert: true },
      );
    }
  }

  async function loadCurrentIfHealthBlocked() {
    if (!currentStateIsLoading()) return false;
    if (typeof window.apiWithFallback !== "function" || typeof window.renderCurrent !== "function") return false;
    const sequence = ++currentBootstrapSequence;
    try {
      const result = await window.apiWithFallback("/api/current", "current");
      if (sequence !== currentBootstrapSequence || !currentStateIsLoading()) return false;
      window.renderCurrent(result, {});
      return true;
    } catch (error) {
      if (sequence !== currentBootstrapSequence || !currentStateIsLoading()) return false;
      markCurrentUnavailable(error);
      return false;
    }
  }

  function scheduleCurrentBootstrap() {
    if (currentBootstrapTimer) clearTimeout(currentBootstrapTimer);
    currentBootstrapTimer = setTimeout(() => {
      currentBootstrapTimer = null;
      void loadCurrentIfHealthBlocked();
    }, CURRENT_BOOTSTRAP_DELAY_MS);
  }

  function siblingScriptUrl(filename) {
    return OBSERVATION_SCRIPT_URL
      ? new URL(filename, OBSERVATION_SCRIPT_URL).href
      : `/static/${filename}`;
  }

  function loadForecastLoadingModule() {
    if (document.querySelector('script[data-rozkalns-forecast-loading="true"]')) return false;
    const script = document.createElement("script");
    script.dataset.rozkalnsForecastLoading = "true";
    script.async = false;
    script.src = OBSERVATION_SCRIPT_URL
      ? new URL("forecast_loading.js", OBSERVATION_SCRIPT_URL).href
      : "/static/forecast_loading.js";
    document.head.appendChild(script);
    return true;
  }

  function loadPwaLifecycleModule() {
    if (document.querySelector('script[data-rozkalns-pwa-lifecycle="true"]')) return false;
    const script = document.createElement("script");
    script.dataset.rozkalnsPwaLifecycle = "true";
    script.async = false;
    script.src = siblingScriptUrl("pwa_lifecycle.js");
    document.head.appendChild(script);
    return true;
  }

  const baseRenderCurrent = window.renderCurrent;
  if (typeof baseRenderCurrent === "function") {
    window.renderCurrent = function renderCurrentWithObservationAge(result, healthMap) {
      baseRenderCurrent(result, healthMap);
      startObservationAgeTicker(result);
    };
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") updateObservationAge(latestResult);
  });

  installCurrentStateCleanupObserver();
  scheduleCurrentBootstrap();
  loadPwaLifecycleModule();
  loadForecastLoadingModule();

  window.RozkalnsObservationAge = Object.freeze({
    OBSERVATION_FRESH_MINUTES,
    TICK_MS,
    CURRENT_BOOTSTRAP_DELAY_MS,
    latestObservationTime,
    ageParts,
    ageLabel,
    staleLabel,
    updateObservationAge,
    startObservationAgeTicker,
    currentStateIsLoading,
    clearUnavailableObservationEvidence,
    currentStateRequiresUnavailableCleanup,
    installCurrentStateCleanupObserver,
    loadCurrentIfHealthBlocked,
    scheduleCurrentBootstrap,
    siblingScriptUrl,
    loadForecastLoadingModule,
    loadPwaLifecycleModule,
  });
})();
