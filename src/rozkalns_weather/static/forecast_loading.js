(() => {
  "use strict";

  const PUBLIC_DEFAULT_LOCATION = "station_05480";
  const FORECAST_LOCATIONS = new Set(["home", "station_05480", "station_10416"]);
  const FORECAST_SCRIPT_URL = document.currentScript?.src || "";
  let forecastSequence = 0;
  let activeTemperature = null;
  let activePrecipitation = null;
  let activeForecastController = null;

  function locationSelector() {
    return document.querySelector("#forecastLocation");
  }

  function providerHealthStillLoading() {
    return document.querySelector("#providerState")?.dataset.state === "loading";
  }

  function normalizeLocation(value) {
    return FORECAST_LOCATIONS.has(value) ? value : PUBLIC_DEFAULT_LOCATION;
  }

  function selectedLocation() {
    return normalizeLocation(locationSelector()?.value);
  }

  function establishPrivacySafeBootstrapLocation() {
    const selector = locationSelector();
    if (!selector) return null;
    if (selector.value === "home" && providerHealthStillLoading()) selector.value = PUBLIC_DEFAULT_LOCATION;
    return selectedLocation();
  }

  function latestRetrieval(rows) {
    return (rows || [])
      .map((row) => row?.retrieved_at_utc)
      .filter(Boolean)
      .sort()
      .at(-1) || null;
  }

  const baseProviderSurfaceState = window.providerSurfaceState;
  if (typeof baseProviderSurfaceState === "function") {
    window.providerSurfaceState = function providerSurfaceStateWithPendingHealth(rows, healthMap, result) {
      const hasHealthEvidence = healthMap && Object.keys(healthMap).length > 0;
      if (hasHealthEvidence) return baseProviderSurfaceState(rows, healthMap, result);

      const fallbackState = typeof window.stateFromResult === "function" ? window.stateFromResult(result) : "fresh";
      if (fallbackState !== "fresh" || !(rows || []).length) {
        return baseProviderSurfaceState(rows, healthMap || {}, result);
      }

      const retrieved = latestRetrieval(rows);
      const formatted = retrieved && typeof window.formatTimestamp === "function"
        ? window.formatTimestamp(retrieved)
        : retrieved;
      return {
        state: "fresh",
        message: `Forecast API response loaded independently; provider health is still pending.${formatted ? ` Latest retrieval ${formatted}.` : ""}`,
      };
    };
  }

  function requestApi() {
    return window.RozkalnsRequestLifecycle?.apiWithTimeoutFallback || window.apiWithFallback;
  }

  function loadRequestLifecycleModule() {
    if (window.RozkalnsRequestLifecycle?.apiWithTimeoutFallback) return Promise.resolve(true);
    const existing = document.querySelector('script[data-rozkalns-request-lifecycle="true"]');
    if (existing) {
      return new Promise((resolve) => {
        existing.addEventListener("load", () => resolve(true), { once: true });
        existing.addEventListener("error", () => resolve(false), { once: true });
      });
    }
    return new Promise((resolve) => {
      const script = document.createElement("script");
      script.dataset.rozkalnsRequestLifecycle = "true";
      script.async = false;
      script.src = FORECAST_SCRIPT_URL
        ? new URL("request_lifecycle.js", FORECAST_SCRIPT_URL).href
        : "/static/request_lifecycle.js";
      script.addEventListener("load", () => resolve(true), { once: true });
      script.addEventListener("error", () => resolve(false), { once: true });
      document.head.appendChild(script);
    });
  }

  function stillCurrent(sequence, locationId) {
    return sequence === forecastSequence && selectedLocation() === locationId;
  }

  function setFailure(ids, label, error) {
    ids.forEach((id) => {
      if (typeof window.setSurfaceState === "function") {
        window.setSurfaceState(
          id,
          navigator.onLine ? "error" : "offline",
          `${label} unavailable: ${error}`,
          { alert: true },
        );
      }
    });
  }

  function clearTemperatureVisuals() {
    const chart = document.querySelector("#modelsChart");
    if (chart) {
      chart.classList.add("empty");
      chart.textContent = "Temperature forecast unavailable for this location.";
    }

    const uncertainty = document.querySelector("#uncertainty");
    if (uncertainty) {
      uncertainty.textContent = "WeatherNext uncertainty unavailable because the temperature forecast failed for this location.";
    }

    const snapshot = document.querySelector("#modelSnapshot");
    if (snapshot) {
      snapshot.textContent = "Model temperature snapshot unavailable for this location.";
    }

    const spread = document.querySelector("#modelSpread");
    if (spread) {
      spread.textContent = "Model spread — · temperature forecast unavailable for this location.";
    }
  }

  function clearOverviewHourlyVisuals() {
    const strip = document.querySelector("#hourlyStrip");
    if (strip) strip.innerHTML = '<div class="empty-card">Next-hours forecast unavailable for this location.</div>';

    const chart = document.querySelector("#consumerHourlyChart");
    if (chart) chart.textContent = "";

    const provider = document.querySelector("#hourlyProvider");
    if (provider) provider.textContent = "Next-hours forecast unavailable for this location.";

    const detail = document.querySelector("#hourlyDetail");
    if (detail) detail.textContent = "Next-hours details unavailable because the selected location forecast is incomplete.";
  }

  function maybeRenderHourly(sequence, locationId) {
    if (!activeTemperature || !activePrecipitation || !stillCurrent(sequence, locationId)) return;
    if (typeof window.renderConsumerHourly === "function") {
      window.renderConsumerHourly(activeTemperature, activePrecipitation, {});
    }
  }

  async function loadTemperature(sequence, locationId, options) {
    try {
      const api = requestApi();
      if (typeof api !== "function") return false;
      const result = await api(
        `/api/hourly?hours=48&variable=temperature_2m&location_id=${locationId}`,
        `hourly-temperature-48-${locationId}`,
        options,
      );
      if (!stillCurrent(sequence, locationId)) return false;
      activeTemperature = result;
      if (typeof window.renderTemperature === "function") window.renderTemperature(result, {});
      if (typeof window.renderModelSnapshot === "function") window.renderModelSnapshot(result.payload?.series || [], {});
      maybeRenderHourly(sequence, locationId);
      return true;
    } catch (error) {
      if (!stillCurrent(sequence, locationId)) return false;
      activeTemperature = null;
      clearTemperatureVisuals();
      clearOverviewHourlyVisuals();
      setFailure(["modelsTempState", "overviewTempState"], "Temperature forecast", error);
      return false;
    }
  }

  async function loadPrecipitation(sequence, locationId, options) {
    try {
      const api = requestApi();
      if (typeof api !== "function") return false;
      const result = await api(
        `/api/hourly?hours=48&variable=precipitation_1h&location_id=${locationId}`,
        `hourly-precipitation-48-${locationId}`,
        options,
      );
      if (!stillCurrent(sequence, locationId)) return false;
      activePrecipitation = result;
      if (typeof window.renderPrecipitation === "function") window.renderPrecipitation(result, {});
      maybeRenderHourly(sequence, locationId);
      return true;
    } catch (error) {
      if (!stillCurrent(sequence, locationId)) return false;
      activePrecipitation = null;
      clearOverviewHourlyVisuals();
      setFailure(["modelsPrecipState", "overviewPrecipState"], "Precipitation forecast", error);
      return false;
    }
  }

  async function loadDaily(sequence, locationId, options) {
    try {
      const api = requestApi();
      if (typeof api !== "function") return false;
      const result = await api(
        `/api/daily?days=14&location_id=${locationId}`,
        `daily-14-${locationId}`,
        options,
      );
      if (!stillCurrent(sequence, locationId)) return false;
      if (typeof window.renderDaily === "function") window.renderDaily(result, {});
      return true;
    } catch (error) {
      if (!stillCurrent(sequence, locationId)) return false;
      const grid = document.querySelector("#dailyGrid");
      const highLow = document.querySelector("#heroHighLow");
      if (grid) grid.textContent = "Daily forecast unavailable.";
      if (highLow) highLow.textContent = "H —° · L —°";
      setFailure(["dailyState"], "Daily forecast", error);
      return false;
    }
  }

  function newForecastRequestOptions() {
    if (activeForecastController) activeForecastController.abort();
    activeForecastController = typeof AbortController === "function" ? new AbortController() : null;
    return activeForecastController ? { signal: activeForecastController.signal } : {};
  }

  function loadForecastSurfaces(locationId = selectedLocation()) {
    const api = requestApi();
    if (typeof api !== "function") return 0;
    const normalized = normalizeLocation(locationId);
    const sequence = ++forecastSequence;
    const options = newForecastRequestOptions();
    activeTemperature = null;
    activePrecipitation = null;
    void loadTemperature(sequence, normalized, options);
    void loadPrecipitation(sequence, normalized, options);
    void loadDaily(sequence, normalized, options);
    return sequence;
  }

  function start() {
    const selector = locationSelector();
    if (!selector) return;
    const locationId = establishPrivacySafeBootstrapLocation();
    if (!locationId) return;
    loadForecastSurfaces(locationId);
    selector.addEventListener("change", () => loadForecastSurfaces(selectedLocation()));
  }

  window.RozkalnsForecastLoading = Object.freeze({
    PUBLIC_DEFAULT_LOCATION,
    normalizeLocation,
    selectedLocation,
    establishPrivacySafeBootstrapLocation,
    loadRequestLifecycleModule,
    loadForecastSurfaces,
  });

  void loadRequestLifecycleModule().finally(start);
})();
