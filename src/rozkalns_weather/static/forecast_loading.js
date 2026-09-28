(() => {
  "use strict";

  const PUBLIC_DEFAULT_LOCATION = "station_05480";
  const FORECAST_LOCATIONS = new Set(["home", "station_05480", "station_10416"]);
  let forecastSequence = 0;
  let activeTemperature = null;
  let activePrecipitation = null;

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

  function maybeRenderHourly(sequence, locationId) {
    if (!activeTemperature || !activePrecipitation || !stillCurrent(sequence, locationId)) return;
    if (typeof window.renderConsumerHourly === "function") {
      window.renderConsumerHourly(activeTemperature, activePrecipitation, {});
    }
  }

  async function loadTemperature(sequence, locationId) {
    try {
      const result = await window.apiWithFallback(
        `/api/hourly?hours=48&variable=temperature_2m&location_id=${locationId}`,
        `hourly-temperature-48-${locationId}`,
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
      setFailure(["modelsTempState", "overviewTempState"], "Temperature forecast", error);
      return false;
    }
  }

  async function loadPrecipitation(sequence, locationId) {
    try {
      const result = await window.apiWithFallback(
        `/api/hourly?hours=48&variable=precipitation_1h&location_id=${locationId}`,
        `hourly-precipitation-48-${locationId}`,
      );
      if (!stillCurrent(sequence, locationId)) return false;
      activePrecipitation = result;
      if (typeof window.renderPrecipitation === "function") window.renderPrecipitation(result, {});
      maybeRenderHourly(sequence, locationId);
      return true;
    } catch (error) {
      if (!stillCurrent(sequence, locationId)) return false;
      activePrecipitation = null;
      setFailure(["modelsPrecipState", "overviewPrecipState"], "Precipitation forecast", error);
      return false;
    }
  }

  async function loadDaily(sequence, locationId) {
    try {
      const result = await window.apiWithFallback(
        `/api/daily?days=14&location_id=${locationId}`,
        `daily-14-${locationId}`,
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

  function loadForecastSurfaces(locationId = selectedLocation()) {
    if (typeof window.apiWithFallback !== "function") return 0;
    const normalized = normalizeLocation(locationId);
    const sequence = ++forecastSequence;
    activeTemperature = null;
    activePrecipitation = null;
    void loadTemperature(sequence, normalized);
    void loadPrecipitation(sequence, normalized);
    void loadDaily(sequence, normalized);
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
    loadForecastSurfaces,
  });

  setTimeout(start, 0);
})();
