(() => {
  "use strict";

  const NOW_WINDOW_MS = 45 * 60 * 1000;
  const PROVIDER_LABELS = Object.freeze({
    weathernext3: "WeatherNext 3",
    icon_d2: "ICON-D2",
    ecmwf_ifs: "ECMWF IFS",
    ecmwf_aifs: "AIFS",
    dwd_mosmix_l: "DWD MOSMIX-L",
  });
  let heroForecastObserver = null;
  let hourlyInteractionSequence = 0;

  function parseTimestamp(value) {
    const stamp = new Date(value).getTime();
    return Number.isFinite(stamp) ? stamp : null;
  }

  function selectNowIndex(rows, nowMs = Date.now()) {
    let best = null;
    (rows || []).forEach((row, index) => {
      const stamp = parseTimestamp(row?.valid_time_utc);
      if (stamp == null) return;
      const delta = stamp - nowMs;
      const distance = Math.abs(delta);
      if (distance > NOW_WINDOW_MS) return;
      const future = delta >= 0;
      const candidate = { index, stamp, distance, future };
      if (
        !best
        || candidate.distance < best.distance
        || (candidate.distance === best.distance && candidate.future && !best.future)
        || (candidate.distance === best.distance && candidate.future === best.future && candidate.stamp < best.stamp)
      ) {
        best = candidate;
      }
    });
    return best ? best.index : -1;
  }

  function berlinLocalTime(value) {
    if (typeof window.formatLocalTime === "function") return window.formatLocalTime(value);
    const stamp = parseTimestamp(value);
    if (stamp == null) return "—";
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Berlin",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(stamp));
  }

  function normalizedProviderUiState(provider) {
    const freshness = provider?.freshness_state || "unknown";
    const ingest = provider?.ingest_state || provider?.state || "unknown";
    const outsideRecurringScope = provider?.reason_code === "NOT_IN_PUBLIC_RECURRING_SCOPE";

    if (freshness === "error" || ingest === "error" || provider?.state === "error") return "error";
    if (["access_pending", "pending"].includes(freshness) || ["access_pending", "pending"].includes(ingest)) return "pending";
    if (
      ["not_tracked", "inactive"].includes(freshness)
      || ["not_tracked", "inactive"].includes(ingest)
      || provider?.tracked === false
      || outsideRecurringScope
    ) return "inactive";
    if (freshness === "fresh") return "fresh";
    if (["lagging", "degraded", "stale", "unknown", "not_ingested"].includes(freshness)) return "stale";
    return "stale";
  }

  if (typeof window.normalizedProviderState === "function") {
    window.normalizedProviderState = normalizedProviderUiState;
  }

  function rerenderProviderCardsIfReady() {
    if (typeof lastHealth === "undefined" || !lastHealth?.providers) return;
    if (typeof window.providersCard !== "function") return;
    const markup = window.providersCard(lastHealth.providers);
    ["providerGrid", "providerClasses"].forEach((id) => {
      const element = document.querySelector(`#${id}`);
      if (element) element.innerHTML = markup;
    });
  }

  function restoreSurface(id) {
    const element = document.querySelector(`#${id}`);
    if (!element) return;
    element.hidden = false;
    element.removeAttribute("aria-hidden");
    delete element.dataset.dedupHidden;
  }

  function surfaceSignature(element) {
    if (!element) return null;
    return `${element.dataset.state || ""}\n${element.textContent.trim()}`;
  }

  function dedupeSurfacePair(primaryId, duplicateId) {
    const primary = document.querySelector(`#${primaryId}`);
    const duplicate = document.querySelector(`#${duplicateId}`);
    if (!primary || !duplicate) return false;

    if (surfaceSignature(primary) !== surfaceSignature(duplicate)) {
      restoreSurface(duplicateId);
      return false;
    }

    duplicate.hidden = true;
    duplicate.dataset.dedupHidden = "true";
    duplicate.setAttribute("aria-hidden", "true");
    duplicate.removeAttribute("role");
    duplicate.removeAttribute("aria-live");
    duplicate.removeAttribute("aria-atomic");
    return true;
  }

  function latestObservationTime(result) {
    return (result?.payload?.observations || [])
      .map((item) => item.observed_at_utc)
      .filter(Boolean)
      .sort()
      .at(-1) || null;
  }

  function compactCurrentObservation(result) {
    const observed = latestObservationTime(result);
    const state = document.querySelector("#currentState");
    const localTime = observed ? berlinLocalTime(observed) : "—";
    const stamp = parseTimestamp(observed);
    const ageMinutes = stamp == null ? null : Math.max(0, Math.round((Date.now() - stamp) / 60000));
    const ageLabel = ageMinutes == null ? "age unknown" : ageMinutes <= 1 ? "just now" : `${ageMinutes} min ago`;

    const heroUpdated = document.querySelector("#heroUpdated");
    if (heroUpdated && state?.dataset.state === "fresh") {
      heroUpdated.textContent = observed
        ? `Observed ${localTime} · ${ageLabel}`
        : "DWD observation unavailable";
    }

    const heroFeels = document.querySelector("#heroFeels");
    if (heroFeels) heroFeels.textContent = "DWD observation";

    const heroIcon = document.querySelector("#heroIcon");
    if (heroIcon) {
      heroIcon.dataset.conditionEvidence = heroIcon.dataset.condition === "unknown"
        ? "observation-unavailable"
        : "observation";
      delete heroIcon.dataset.forecastProvider;
      delete heroIcon.dataset.forecastValidTimeUtc;
      delete heroIcon.dataset.forecastInitTimeUtc;
      delete heroIcon.dataset.forecastRetrievedAtUtc;
    }

    if (!state) return;
    state.classList.add("compact-state");

    if (state.dataset.state === "fresh") {
      state.textContent = "DWD observation current";
      state.hidden = true;
      state.dataset.dedupHidden = "true";
      state.setAttribute("aria-hidden", "true");
      state.removeAttribute("role");
      state.removeAttribute("aria-live");
      state.removeAttribute("aria-atomic");
    } else if (state.dataset.state === "stale") {
      state.textContent = observed
        ? "STALE · DWD observation is not current"
        : "STALE · DWD observation unavailable";
    } else if (state.dataset.state === "error") {
      state.textContent = observed
        ? "ERROR · DWD observation provider degraded"
        : "ERROR · DWD observation unavailable";
    } else if (state.dataset.state === "offline") {
      state.textContent = observed
        ? "OFFLINE · showing last DWD observation · not current"
        : "OFFLINE · DWD observation unavailable";
    }
  }

  function providerLabel(provider, row) {
    return row?.model_name || PROVIDER_LABELS[provider] || provider || "Forecast model";
  }

  function numericRowValue(row) {
    if (!row || row.value == null || row.value === "") return null;
    const value = Number(row.value);
    return Number.isFinite(value) ? value : null;
  }

  function canonicalRowsForProvider(rows, provider) {
    if (!provider) return [];
    if (typeof window.canonicalProviderRows === "function") {
      return window.canonicalProviderRows(rows || [], provider);
    }
    return (rows || [])
      .filter((row) => row?.provider === provider)
      .slice()
      .sort((a, b) => String(a.valid_time_utc || "").localeCompare(String(b.valid_time_utc || "")));
  }

  function rowsByValidTime(rows, provider) {
    return new Map(canonicalRowsForProvider(rows, provider).map((row) => [row.valid_time_utc, row]));
  }

  function sameForecastRun(anchor, row) {
    if (!anchor || !row || anchor.provider !== row.provider) return false;
    if (anchor.init_time_utc && row.init_time_utc && anchor.init_time_utc !== row.init_time_utc) return false;
    if (anchor.model_version && row.model_version && anchor.model_version !== row.model_version) return false;
    return true;
  }

  function injectHourlyInteractionStyles() {
    if (document.querySelector("#rozkalns-hourly-interaction-style")) return;
    const style = document.createElement("style");
    style.id = "rozkalns-hourly-interaction-style";
    style.textContent = `
      #hourlyStrip .hour-card[role="button"]{color:inherit;cursor:pointer;outline:none}
      #hourlyStrip .hour-card[role="button"]:focus-visible{outline:2px solid var(--blue,#2f9fff);outline-offset:2px}
      #hourlyStrip .hour-card[aria-pressed="true"]{border-color:#2f9fff;box-shadow:inset 0 0 0 1px rgba(47,159,255,.28),0 0 18px rgba(47,159,255,.1)}
      .hourly-detail{margin:2px 1px 9px;padding:10px 11px;border:1px solid rgba(74,132,180,.28);border-radius:12px;background:rgba(11,37,61,.58);color:inherit}
      .hourly-detail-head{display:flex;justify-content:space-between;gap:10px;align-items:baseline;margin-bottom:7px}
      .hourly-detail-head span,.hourly-detail-source,.hourly-detail-note{color:#91a9c2;font-size:.68rem;line-height:1.35;overflow-wrap:anywhere}
      .hourly-detail-values{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-bottom:7px}
      .hourly-detail-metric{padding:7px 8px;border:1px solid rgba(60,115,160,.2);border-radius:9px;background:rgba(8,29,49,.46)}
      .hourly-detail-metric small,.hourly-detail-metric strong,.hourly-detail-metric span{display:block}
      .hourly-detail-metric small{color:#8faac3;font-size:.64rem}.hourly-detail-metric strong{margin-top:2px;font-size:.9rem}.hourly-detail-metric span{margin-top:2px;color:#91a9c2;font-size:.6rem}
      @media(max-width:420px){.hourly-detail-head{align-items:flex-start;flex-direction:column;gap:2px}.hourly-detail-metric{padding:6px 5px}}
    `;
    document.head.appendChild(style);
  }

  function ensureHourlyDetailTarget(strip) {
    let target = document.querySelector("#hourlyDetail");
    if (target) return target;
    target = document.createElement("div");
    target.id = "hourlyDetail";
    target.className = "hourly-detail";
    target.setAttribute("role", "status");
    target.setAttribute("aria-live", "polite");
    target.setAttribute("aria-atomic", "true");
    strip.insertAdjacentElement("afterend", target);
    return target;
  }

  function appendHourlyMetric(container, label, value, note = "") {
    const metric = document.createElement("div");
    metric.className = "hourly-detail-metric";
    const heading = document.createElement("small");
    heading.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = value;
    metric.append(heading, strong);
    if (note) {
      const description = document.createElement("span");
      description.textContent = note;
      metric.append(description);
    }
    container.append(metric);
  }

  function renderHourlyDetail(target, { anchor, precipRow, windRow, windState, provider }) {
    target.replaceChildren();
    if (!anchor) {
      target.textContent = "Select an available forecast hour for details.";
      return;
    }

    const modelName = providerLabel(provider, anchor);
    const heading = document.createElement("div");
    heading.className = "hourly-detail-head";
    const title = document.createElement("strong");
    title.textContent = `${berlinLocalTime(anchor.valid_time_utc)} · Europe/Berlin`;
    const model = document.createElement("span");
    model.textContent = modelName;
    heading.append(title, model);

    const values = document.createElement("div");
    values.className = "hourly-detail-values";
    const temperature = numericRowValue(anchor);
    appendHourlyMetric(values, "Temperature", temperature == null ? "—" : `${Math.round(temperature)} °C`, temperature == null ? "value unavailable" : "forecast");

    const sameRunPrecip = sameForecastRun(anchor, precipRow) ? precipRow : null;
    const precipitation = numericRowValue(sameRunPrecip);
    appendHourlyMetric(
      values,
      "Precipitation",
      precipitation == null ? "—" : `${precipitation.toFixed(1)} mm`,
      precipitation == null ? "same-run value unavailable" : "amount, not probability",
    );

    const sameRunWind = sameForecastRun(anchor, windRow) ? windRow : null;
    const wind = numericRowValue(sameRunWind);
    const windNote = wind == null
      ? (windState === "loading" ? "loading wind data" : "wind data unavailable")
      : `${wind.toFixed(1)} m/s source${windState === "cached" ? " · cached" : ""}`;
    appendHourlyMetric(values, "Wind", wind == null ? "—" : `${Math.round(wind * 3.6)} km/h`, windNote);

    const source = document.createElement("div");
    source.className = "hourly-detail-source";
    const lead = Number(anchor.lead_hours);
    const leadLabel = Number.isFinite(lead) ? `${Number.isInteger(lead) ? lead.toFixed(0) : lead.toFixed(1)} h` : "—";
    source.textContent = `${modelName} · forecast for ${berlinLocalTime(anchor.valid_time_utc)}`;

    target.append(heading, values, source);
  }

  function enhanceHourlyInteraction({ tempResult, precipResult, provider, tempSeries, cards, selectedIndex }) {
    const strip = document.querySelector("#hourlyStrip");
    if (!strip || !provider || !tempSeries.length || !cards.length) return;
    injectHourlyInteractionStyles();
    const target = ensureHourlyDetailTarget(strip);
    const sequence = ++hourlyInteractionSequence;
    const locationId = tempResult?.payload?.location?.id || "station_05480";
    const precipByTime = rowsByValidTime(precipResult?.payload?.series || [], provider);
    let windByTime = new Map();
    let windState = "loading";
    let activeIndex = selectedIndex >= 0 && selectedIndex < cards.length ? selectedIndex : 0;

    function renderSelected() {
      const anchor = tempSeries[activeIndex];
      renderHourlyDetail(target, {
        anchor,
        precipRow: precipByTime.get(anchor?.valid_time_utc),
        windRow: windByTime.get(anchor?.valid_time_utc),
        windState,
        provider,
      });
    }

    function activate(index) {
      if (index < 0 || index >= cards.length) return;
      activeIndex = index;
      cards.forEach((card, cardIndex) => card.setAttribute("aria-pressed", String(cardIndex === activeIndex)));
      renderSelected();
    }

    cards.forEach((card, index) => {
      const row = tempSeries[index];
      if (!row) return;
      const precipRow = precipByTime.get(row.valid_time_utc);
      const precipitation = numericRowValue(sameForecastRun(row, precipRow) ? precipRow : null);
      const temperature = numericRowValue(row);
      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");
      card.setAttribute("aria-controls", target.id);
      card.setAttribute("aria-pressed", String(index === activeIndex));
      card.dataset.provider = provider;
      const timeLabel = card.querySelector(".hour-label")?.textContent?.trim() || berlinLocalTime(row.valid_time_utc);
      const tempLabel = temperature == null ? "temperature unavailable" : `${Math.round(temperature)} degrees Celsius`;
      const rainLabel = precipitation == null ? "precipitation unavailable" : `${precipitation.toFixed(1)} millimetres precipitation`;
      card.setAttribute("aria-label", `${timeLabel}; ${tempLabel}; ${rainLabel}; show hourly forecast details`);
      card.addEventListener("click", () => activate(index));
      card.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        activate(index);
      });
    });
    renderSelected();

    if (typeof window.apiWithFallback !== "function") {
      windState = "unavailable";
      renderSelected();
      return;
    }

    window.apiWithFallback(
      `/api/hourly?hours=48&variable=wind_speed_10m&location_id=${encodeURIComponent(locationId)}`,
      `hourly-wind-48-${locationId}`,
    ).then((result) => {
      if (sequence !== hourlyInteractionSequence) return;
      windByTime = rowsByValidTime(result?.payload?.series || [], provider);
      windState = result?.source && result.source !== "network" ? "cached" : "available";
      renderSelected();
    }).catch(() => {
      if (sequence !== hourlyInteractionSequence) return;
      windByTime = new Map();
      windState = "unavailable";
      renderSelected();
    });
  }

  function disconnectHeroForecastObserver() {
    if (!heroForecastObserver) return;
    heroForecastObserver.disconnect();
    heroForecastObserver = null;
  }

  function applyForecastHeroFromNowCard(provider, tempSeries, nowIndex, cards) {
    const heroIcon = document.querySelector("#heroIcon");
    const heroCondition = document.querySelector("#heroCondition");
    if (!heroIcon || !heroCondition) return false;

    // A real aligned DWD observed condition always wins. Forecast evidence is
    // only a presentation fallback while the observation condition is unknown.
    if (heroIcon.dataset.condition && heroIcon.dataset.condition !== "unknown") return true;
    if (nowIndex < 0) return false;

    const row = tempSeries[nowIndex];
    const card = cards[nowIndex];
    const condition = card?.dataset.condition;
    const daylight = card?.dataset.daylight || "unknown";
    if (!row || !card || !condition || condition === "unknown") return false;

    const hourIcon = card.querySelector(".hour-icon");
    const conditionSource = hourIcon?.dataset.conditionSource || "same_run_forecast_condition";
    const visibleCondition = hourIcon?.querySelector("svg[aria-label]")?.getAttribute("aria-label") || "Forecast conditions";
    const modelName = providerLabel(provider, row);
    const label = `${visibleCondition} · ${modelName} forecast`;
    const weatherUi = window.RozkalnsWeatherConditions;
    if (!weatherUi?.weatherIcon) return false;

    heroCondition.textContent = label;
    heroCondition.title = `Forecast condition at ${berlinLocalTime(row.valid_time_utc)} because the current DWD observation has no aligned condition evidence.`;
    heroIcon.innerHTML = weatherUi.weatherIcon(condition, daylight, { label, decorative: true });
    heroIcon.dataset.condition = condition;
    heroIcon.dataset.daylight = daylight;
    heroIcon.dataset.conditionEvidence = "forecast";
    heroIcon.dataset.conditionSource = conditionSource;
    heroIcon.dataset.forecastProvider = provider || "unknown";
    heroIcon.dataset.forecastValidTimeUtc = row.valid_time_utc || "";
    heroIcon.dataset.forecastInitTimeUtc = row.init_time_utc || "";
    heroIcon.dataset.forecastRetrievedAtUtc = row.retrieved_at_utc || "";
    return true;
  }

  function watchForForecastHeroFallback(provider, tempSeries, nowIndex, cards) {
    disconnectHeroForecastObserver();
    if (applyForecastHeroFromNowCard(provider, tempSeries, nowIndex, cards)) return;
    if (nowIndex < 0 || typeof MutationObserver === "undefined") return;

    const strip = document.querySelector("#hourlyStrip");
    if (!strip) return;
    heroForecastObserver = new MutationObserver(() => {
      if (applyForecastHeroFromNowCard(provider, tempSeries, nowIndex, cards)) {
        disconnectHeroForecastObserver();
      }
    });
    heroForecastObserver.observe(strip, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["data-condition", "data-daylight", "data-condition-source"],
    });
  }

  const baseSetSurfaceState = window.setSurfaceState;
  if (typeof baseSetSurfaceState === "function") {
    window.setSurfaceState = function setSurfaceStateWithDedupReset(id, ...args) {
      restoreSurface(id);
      return baseSetSurfaceState(id, ...args);
    };
  }

  const baseRenderCurrent = window.renderCurrent;
  if (typeof baseRenderCurrent === "function") {
    window.renderCurrent = function renderCurrentWithConsumerProvenance(result, healthMap) {
      disconnectHeroForecastObserver();
      baseRenderCurrent(result, healthMap);
      compactCurrentObservation(result);
    };
  }

  const baseRenderConsumerHourly = window.renderConsumerHourly;
  if (typeof baseRenderConsumerHourly === "function") {
    window.renderConsumerHourly = function renderConsumerHourlySingleNow(tempResult, precipResult, healthMap) {
      baseRenderConsumerHourly(tempResult, precipResult, healthMap);

      const tempRows = tempResult?.payload?.series || [];
      const precipRows = precipResult?.payload?.series || [];
      const provider = typeof window.chooseProvider === "function"
        ? window.chooseProvider(tempRows, precipRows)
        : null;
      const canonical = provider && typeof window.canonicalProviderRows === "function"
        ? window.canonicalProviderRows(tempRows, provider)
        : [];
      const tempSeries = typeof window.futureRows === "function"
        ? window.futureRows(canonical, 8)
        : canonical.slice(0, 8);
      const nowIndex = selectNowIndex(tempSeries, Date.now());
      const cards = [...document.querySelectorAll("#hourlyStrip .hour-card")];

      cards.forEach((card, index) => {
        const row = tempSeries[index];
        if (!row) return;
        const isNow = index === nowIndex;
        card.classList.toggle("now", isNow);
        card.dataset.validTimeUtc = row.valid_time_utc;
        const label = card.querySelector(".hour-label");
        if (label) label.textContent = isNow ? "Now" : berlinLocalTime(row.valid_time_utc);
      });

      enhanceHourlyInteraction({
        tempResult,
        precipResult,
        provider,
        tempSeries,
        cards,
        selectedIndex: nowIndex,
      });
      watchForForecastHeroFallback(provider, tempSeries, nowIndex, cards);
      dedupeSurfacePair("overviewTempState", "overviewPrecipState");
    };
  }

  const baseRenderDaily = window.renderDaily;
  if (typeof baseRenderDaily === "function") {
    window.renderDaily = function renderDailyWithForecastLabel(result, healthMap) {
      baseRenderDaily(result, healthMap);
      const highLow = document.querySelector("#heroHighLow");
      if (highLow && !highLow.textContent.startsWith("Today forecast ·")) {
        highLow.textContent = `Today forecast · ${highLow.textContent}`;
      }
    };
  }

  const baseGlobalNetworkState = window.globalNetworkState;
  if (typeof baseGlobalNetworkState === "function") {
    window.globalNetworkState = function globalNetworkStateWithoutDuplicateProviderSummary(healthState) {
      baseGlobalNetworkState(healthState);
      dedupeSurfacePair("providerState", "networkState");
    };
  }

  rerenderProviderCardsIfReady();

  window.RozkalnsConsumerUI = Object.freeze({
    NOW_WINDOW_MS,
    selectNowIndex,
    normalizedProviderUiState,
    dedupeSurfacePair,
    compactCurrentObservation,
    applyForecastHeroFromNowCard,
    numericRowValue,
    sameForecastRun,
    enhanceHourlyInteraction,
  });
})();
