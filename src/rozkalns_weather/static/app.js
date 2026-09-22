const qs = (selector) => document.querySelector(selector);
const qsa = (selector) => [...document.querySelectorAll(selector)];

const DATA_CACHE_PREFIX = "rozkalns-weather:pwa-cache:v1:";
const UI_STATES = ["loading", "fresh", "stale", "error", "offline"];
const PUBLIC_PROVIDER_IDS = new Set(["dwd_observations", "dwd_mosmix_l", "icon_d2", "ecmwf_ifs", "ecmwf_aifs"]);
const PROVIDER_PREFERENCE = ["weathernext3", "icon_d2", "ecmwf_ifs", "ecmwf_aifs", "dwd_mosmix_l"];
const MODEL_SNAPSHOT_IDS = ["weathernext3", "icon_d2", "ecmwf_ifs", "ecmwf_aifs"];
const MODEL_LABELS = {
  weathernext3: "WeatherNext 3",
  icon_d2: "ICON-D2",
  ecmwf_ifs: "ECMWF IFS",
  ecmwf_aifs: "AIFS",
  dwd_mosmix_l: "DWD MOSMIX-L",
};
const STAT_PREFERENCE = ["deterministic", "mean", "p50"];
const OBSERVATION_FRESH_HOURS = 3;
const FORECAST_LOCATION_META = {
  home: {
    label: "Home",
    heroLabel: "Dortmund-Wickede",
    note: "Privāta home prognoze; nav izmērīta station accuracy.",
  },
  station_05480: {
    label: "DWD CDC 05480",
    heroLabel: "Dortmund-Wickede · reference",
    note: "Canonical public benchmark; station prognozes salīdzina pret DWD CDC 05480 observations.",
  },
  station_10416: {
    label: "DWD 10416 · legacy MOSMIX",
    heroLabel: "Dortmund · legacy 10416",
    note: "Legacy MOSMIX reference; nav pašreizējais measured benchmark.",
  },
};

const loadedSafetySurfaces = new Set();
let lastHealth = null;
let forecastLocationInitialized = false;
let refreshSequence = 0;
let accuracyLoaded = false;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

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

async function apiWithFallback(url, cacheKey) {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const payload = await response.json();
    return { payload, source: "network", cached_at_utc: storageWrite(cacheKey, payload), error: null };
  } catch (error) {
    const cached = storageRead(cacheKey);
    if (!cached) throw error;
    return {
      payload: cached.payload,
      source: navigator.onLine ? "stale-cache" : "offline-cache",
      cached_at_utc: cached.cached_at_utc,
      error: String(error),
    };
  }
}

function stateFromResult(result) {
  if (!result) return "error";
  if (result.source === "offline-cache") return "offline";
  if (result.source === "stale-cache") return "stale";
  return "fresh";
}

function setSurfaceState(id, state, message, { alert = false } = {}) {
  const element = qs(`#${id}`);
  if (!element) return;
  UI_STATES.forEach((item) => element.classList.remove(`state-${item}`));
  element.classList.add("surface-state", `state-${state}`);
  element.dataset.state = state;
  element.setAttribute("role", alert ? "alert" : "status");
  element.setAttribute("aria-live", alert ? "assertive" : "polite");
  element.setAttribute("aria-atomic", "true");
  element.textContent = `${state.toUpperCase()} · ${message}`;
}

function berlinDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? null : date;
}

function formatTimestamp(value) {
  const date = berlinDate(value);
  if (!date) return value ? String(value) : "unknown time";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Berlin",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatLocalTime(value) {
  const date = berlinDate(value);
  if (!date) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Berlin",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function localDateKey(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Berlin",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const map = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${map.year}-${map.month}-${map.day}`;
}

function cacheMessage(result) {
  return `cached ${formatTimestamp(result.cached_at_utc)}`;
}

function ageHours(value) {
  const date = berlinDate(value);
  if (!date) return null;
  return Math.max(0, (Date.now() - date.getTime()) / 3600000);
}

function normalizedProviderState(provider) {
  const freshness = provider?.freshness_state || "unknown";
  if (freshness === "fresh") return "fresh";
  if (freshness === "error") return "error";
  if (["lagging", "degraded", "stale", "unknown", "not_ingested", "not_tracked"].includes(freshness)) return "stale";
  if (provider?.state === "error") return "error";
  return "stale";
}

function providerHealthMap(health) {
  return Object.fromEntries((health?.providers || []).map((provider) => [provider.id, provider]));
}

function providerSurfaceState(rows, healthMap, result) {
  const fallbackState = stateFromResult(result);
  const latestRetrieved = rows.map((row) => row.retrieved_at_utc).filter(Boolean).sort().at(-1) || null;
  if (fallbackState !== "fresh") {
    return {
      state: fallbackState,
      message: `${cacheMessage(result)}; latest stored retrieval ${formatTimestamp(latestRetrieved)}. Data is not current.`,
    };
  }
  if (!rows.length) return { state: "stale", message: "No stored forecast rows are available for this surface." };
  const providers = [...new Set(rows.map((row) => row.provider).filter(Boolean))];
  const degraded = providers.filter((provider) => normalizedProviderState(healthMap[provider]) !== "fresh");
  if (degraded.length === providers.length && !providers.includes("weathernext3")) {
    return {
      state: "stale",
      message: `Displayed provider freshness is degraded (${degraded.join(", ")}); latest retrieval ${formatTimestamp(latestRetrieved)}.`,
    };
  }
  if (degraded.length) {
    return {
      state: "stale",
      message: `Healthy providers remain visible; degraded: ${degraded.join(", ")}. Latest retrieval ${formatTimestamp(latestRetrieved)}.`,
    };
  }
  return { state: "fresh", message: `Live API response; latest retrieval ${formatTimestamp(latestRetrieved)}.` };
}

function providerGridState(health, result) {
  const fallbackState = stateFromResult(result);
  if (fallbackState !== "fresh") return { state: fallbackState, message: `${cacheMessage(result)}; provider status is not current.` };
  const tracked = (health.providers || []).filter((provider) => PUBLIC_PROVIDER_IDS.has(provider.id));
  if (!tracked.length) return { state: "error", message: "Public provider health evidence is missing." };
  const degraded = tracked.filter((provider) => normalizedProviderState(provider) !== "fresh");
  if (!degraded.length) return { state: "fresh", message: "All recurring public providers report fresh state." };
  if (degraded.length === tracked.length) return { state: "stale", message: "All recurring public providers are degraded or not yet fresh." };
  return { state: "stale", message: `Partial provider degradation: ${degraded.map((provider) => provider.id).join(", ")}. Healthy providers remain visible.` };
}

function globalNetworkState(healthState) {
  if (!navigator.onLine) {
    setSurfaceState("networkState", "offline", "Browser reports offline. Last-known data is shown only when a visible cache timestamp is available.", { alert: true });
    return;
  }
  setSurfaceState("networkState", healthState.state, healthState.message, { alert: healthState.state === "error" });
}

function providersCard(items) {
  return items.map((provider) => {
    const uiState = normalizedProviderState(provider);
    return `
      <div class="provider provider-state-${uiState}">
        <div class="provider-heading"><strong>${escapeHtml(provider.model_name)}</strong><span class="state-chip state-${uiState}">${uiState}</span></div>
        <small>
          ingest ${escapeHtml(provider.ingest_state || provider.state || "unknown")}
          <br>freshness ${escapeHtml(provider.freshness_state || "unknown")}
          ${provider.failure_domain && provider.failure_domain !== "none" ? `<br>domain ${escapeHtml(provider.failure_domain)}` : ""}
          ${provider.reason_code ? `<br>${escapeHtml(provider.reason_code)}` : ""}
          ${provider.last_init_time_utc ? `<br>init ${escapeHtml(provider.last_init_time_utc)}` : ""}
          ${provider.last_retrieved_at_utc ? `<br>retrieved ${escapeHtml(provider.last_retrieved_at_utc)}` : ""}
        </small>
      </div>`;
  }).join("");
}

function setActiveView(viewId) {
  qsa(".tabs button").forEach((button) => button.classList.toggle("active", button.dataset.view === viewId));
  qsa(".view").forEach((view) => view.classList.toggle("active", view.id === viewId));
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (viewId === "accuracy" && !accuracyLoaded) {
    accuracyLoaded = true;
    accuracy(30);
  }
}

qsa(".tabs button").forEach((button) => {
  button.onclick = () => setActiveView(button.dataset.view);
});
qsa("[data-open-view]").forEach((button) => {
  button.onclick = () => setActiveView(button.dataset.openView);
});

function observationMap(items) {
  const output = {};
  (items || []).forEach((item) => { output[item.variable] = item; });
  return output;
}

function observedCondition(items) {
  const values = observationMap(items);
  const precip = Number(values.precipitation_1h?.value);
  const cloud = Number(values.cloud_cover?.value);
  if (Number.isFinite(precip) && precip > 0.1) return { label: "Rain observed", icon: "🌧️" };
  if (Number.isFinite(cloud)) {
    if (cloud >= 80) return { label: "Cloudy", icon: "☁️" };
    if (cloud >= 45) return { label: "Partly cloudy", icon: "🌤️" };
    if (cloud >= 20) return { label: "Mostly clear", icon: "🌤️" };
    return { label: "Clear", icon: "☀️" };
  }
  return { label: "Observed conditions", icon: "◌" };
}

function detailValue(row, formatter) {
  if (!row || row.value == null || !Number.isFinite(Number(row.value))) return "—";
  return formatter(Number(row.value));
}

function renderCurrent(result, healthMap) {
  const current = result.payload;
  const items = current.observations || [];
  const values = observationMap(items);
  const observed = items.map((item) => item.observed_at_utc).filter(Boolean).sort().at(-1) || null;
  const age = ageHours(observed);
  const fallbackState = stateFromResult(result);
  const dwdHealth = healthMap.dwd_observations;
  const condition = observedCondition(items);
  const temp = values.temperature_2m;

  qs("#heroTemperature").textContent = temp && Number.isFinite(Number(temp.value)) ? `${Math.round(Number(temp.value))}°` : "—°";
  qs("#heroCondition").textContent = condition.label;
  qs("#heroCondition").title = "Condition label is derived from observed DWD precipitation/cloud-cover values when available.";
  qs("#heroIcon").textContent = condition.icon;
  qs("#heroFeels").textContent = observed ? `Observed ${formatLocalTime(observed)} · Europe/Berlin` : "No DWD observation available";
  qs("#heroSource").textContent = `${current.truth_source || "DWD CDC 05480"} · ${current.location?.label || "Werl"}`;

  qs("#detailHumidity").textContent = detailValue(values.relative_humidity_2m, (value) => `${Math.round(value)}%`);
  qs("#detailWind").textContent = detailValue(values.wind_speed_10m, (value) => `${(value * 3.6).toFixed(0)} km/h`);
  qs("#detailPressure").textContent = detailValue(values.pressure_msl, (value) => `${value.toFixed(0)} hPa`);
  qs("#detailRain").textContent = detailValue(values.precipitation_1h, (value) => `${value.toFixed(1)} mm`);
  qs("#detailCloud").textContent = detailValue(values.cloud_cover, (value) => `${Math.round(value)}%`);
  qs("#detailGust").textContent = detailValue(values.wind_gust_10m, (value) => `${(value * 3.6).toFixed(0)} km/h`);

  if (!items.length) {
    qs("#heroUpdated").textContent = "No DWD observation stored";
    setSurfaceState("currentState", "stale", "No stored DWD CDC 05480 observation is available yet.");
    return;
  }
  if (fallbackState !== "fresh") {
    qs("#heroUpdated").textContent = `${cacheMessage(result)} · not current`;
    setSurfaceState("currentState", fallbackState, `${cacheMessage(result)}; DWD CDC 05480 observation ${formatTimestamp(observed)}. This is not current live evidence.`);
    return;
  }
  if (dwdHealth?.freshness_state === "error" || dwdHealth?.state === "error") {
    qs("#heroUpdated").textContent = `Observed ${formatLocalTime(observed)} · provider degraded`;
    setSurfaceState("currentState", "error", `Latest DWD observation ${formatTimestamp(observed)}; provider health reports an error.`, { alert: true });
    return;
  }
  if (age == null || age > OBSERVATION_FRESH_HOURS) {
    const ageLabel = age == null ? "unknown age" : `${Math.floor(age)} h old`;
    qs("#heroUpdated").textContent = `Latest observation ${formatLocalTime(observed)} · ${ageLabel}`;
    setSurfaceState("currentState", "stale", `Latest DWD observation ${formatTimestamp(observed)} is ${ageLabel}; it is not labelled as current-now.`);
    return;
  }
  const ageMinutes = Math.max(0, Math.round(age * 60));
  qs("#heroUpdated").textContent = `Updated ${formatLocalTime(observed)} · ${ageMinutes <= 5 ? "fresh" : `${ageMinutes} min ago`}`;
  setSurfaceState("currentState", "fresh", `Latest DWD observation ${formatTimestamp(observed)}; observation age ${ageMinutes} min.`);
}

function statisticRank(statistic) {
  const rank = STAT_PREFERENCE.indexOf(statistic);
  return rank === -1 ? 999 : rank;
}

function canonicalProviderRows(rows, providerId) {
  const selected = new Map();
  rows.filter((row) => row.provider === providerId && STAT_PREFERENCE.includes(row.statistic)).forEach((row) => {
    const existing = selected.get(row.valid_time_utc);
    if (!existing || statisticRank(row.statistic) < statisticRank(existing.statistic)) selected.set(row.valid_time_utc, row);
  });
  return [...selected.values()].sort((a, b) => String(a.valid_time_utc).localeCompare(String(b.valid_time_utc)));
}

function chooseProvider(rows, requiredRows = null) {
  const available = new Set(rows.map((row) => row.provider));
  const required = requiredRows ? new Set(requiredRows.map((row) => row.provider)) : null;
  return PROVIDER_PREFERENCE.find((provider) => available.has(provider) && (!required || required.has(provider)))
    || PROVIDER_PREFERENCE.find((provider) => available.has(provider))
    || [...available][0]
    || null;
}

function futureRows(rows, count = 8) {
  if (!rows.length) return [];
  const cutoff = Date.now() - 30 * 60 * 1000;
  const upcoming = rows.filter((row) => {
    const date = berlinDate(row.valid_time_utc);
    return date && date.getTime() >= cutoff;
  });
  return (upcoming.length ? upcoming : rows.slice(-count)).slice(0, count);
}

function rainIcon(amount) {
  if (!Number.isFinite(amount)) return "·";
  if (amount >= 2) return "🌧️";
  if (amount > 0.05) return "🌦️";
  return "○";
}

function renderConsumerHourly(tempResult, precipResult, healthMap) {
  const tempRows = tempResult.payload.series || [];
  const precipRows = precipResult.payload.series || [];
  const provider = chooseProvider(tempRows, precipRows);
  const tempSeries = provider ? futureRows(canonicalProviderRows(tempRows, provider), 8) : [];
  const precipSeries = provider ? canonicalProviderRows(precipRows, provider) : [];
  const precipByTime = new Map(precipSeries.map((row) => [row.valid_time_utc, Number(row.value)]));
  const modelName = tempSeries[0]?.model_name || MODEL_LABELS[provider] || provider || "Provider unavailable";
  qs("#hourlyProvider").textContent = provider ? `${modelName} · precipitation shown as amount (mm), not probability` : "No current forecast provider";

  if (!tempSeries.length) {
    qs("#hourlyStrip").innerHTML = '<div class="empty-card">No forecast points available.</div>';
    qs("#consumerHourlyChart").innerHTML = "";
    return;
  }

  const now = Date.now();
  qs("#hourlyStrip").innerHTML = tempSeries.map((row, index) => {
    const date = berlinDate(row.valid_time_utc);
    const isNearNow = date && Math.abs(date.getTime() - now) <= 45 * 60 * 1000;
    const rain = precipByTime.has(row.valid_time_utc) ? precipByTime.get(row.valid_time_utc) : NaN;
    return `<div class="hour-card ${isNearNow || index === 0 ? "now" : ""}">
      <div class="hour-label">${isNearNow ? "Now" : escapeHtml(formatLocalTime(row.valid_time_utc))}</div>
      <div class="hour-icon">${rainIcon(rain)}</div>
      <strong>${Math.round(Number(row.value))}°</strong>
      <small>${Number.isFinite(rain) ? `${rain.toFixed(1)} mm` : "— mm"}</small>
    </div>`;
  }).join("");

  const temps = tempSeries.map((row) => Number(row.value));
  const rains = tempSeries.map((row) => precipByTime.get(row.valid_time_utc) ?? 0);
  const min = Math.min(...temps);
  const max = Math.max(...temps);
  const range = Math.max(1, max - min);
  const maxRain = Math.max(0.1, ...rains);
  const width = 680;
  const left = 22;
  const right = width - 16;
  const x = (index) => left + (index / Math.max(1, tempSeries.length - 1)) * (right - left);
  const y = (value) => 52 - ((value - min) / range) * 27;
  const path = tempSeries.map((row, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(Number(row.value)).toFixed(1)}`).join(" ");
  const bars = rains.map((value, index) => {
    const height = Math.max(1, (value / maxRain) * 24);
    return `<rect x="${(x(index) - 4).toFixed(1)}" y="${(96 - height).toFixed(1)}" width="8" height="${height.toFixed(1)}" rx="2" fill="#268fff" opacity="${value > 0 ? ".9" : ".25"}"/>`;
  }).join("");
  const points = tempSeries.map((row, index) => `<circle cx="${x(index).toFixed(1)}" cy="${y(Number(row.value)).toFixed(1)}" r="3" fill="#e8f6ff" stroke="#2f9fff" stroke-width="2"/>`).join("");
  qs("#consumerHourlyChart").innerHTML = `<svg viewBox="0 0 ${width} 104" role="img" aria-label="${escapeHtml(modelName)} next-hours temperature line and precipitation amount bars"><path d="${path}" fill="none" stroke="#bde6ff" stroke-width="2"/>${points}${bars}<line x1="${left}" y1="97" x2="${right}" y2="97" stroke="#21435f"/></svg>`;

  const tempState = providerSurfaceState(tempRows.filter((row) => row.provider === provider), healthMap, tempResult);
  const precipState = providerSurfaceState(precipRows.filter((row) => row.provider === provider), healthMap, precipResult);
  setSurfaceState("overviewTempState", tempState.state, `${modelName}: ${tempState.message}`);
  setSurfaceState("overviewPrecipState", precipState.state, `${modelName}: ${precipState.message}`);
}

function dayLabel(dateString) {
  const today = localDateKey();
  if (dateString === today) return "Today";
  const date = new Date(`${dateString}T12:00:00Z`);
  return new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Berlin", weekday: "short" }).format(date);
}

function renderDaily(result, healthMap) {
  const rows = result.payload.days_by_provider || [];
  const provider = chooseProvider(rows);
  const selected = provider ? rows.filter((row) => row.provider === provider).sort((a, b) => String(a.date).localeCompare(String(b.date))).slice(0, 5) : [];
  const modelName = selected[0]?.model_name || MODEL_LABELS[provider] || provider || "Provider unavailable";
  qs("#dailyProvider").textContent = provider ? `${modelName} · min/max and precipitation total` : "No daily provider";

  const state = providerSurfaceState(provider ? rows.filter((row) => row.provider === provider) : [], healthMap, result);
  setSurfaceState("dailyState", state.state, provider ? `${modelName}: ${state.message}` : state.message);

  if (!selected.length) {
    qs("#dailyGrid").textContent = "No daily forecast data available.";
    qs("#heroHighLow").textContent = "H —° · L —°";
    return;
  }

  const numericMins = selected.map((row) => Number(row.temperature_min_c)).filter(Number.isFinite);
  const numericMaxs = selected.map((row) => Number(row.temperature_max_c)).filter(Number.isFinite);
  const globalMin = Math.min(...numericMins);
  const globalMax = Math.max(...numericMaxs);
  const globalRange = Math.max(1, globalMax - globalMin);
  qs("#dailyGrid").innerHTML = selected.map((row) => {
    const min = Number(row.temperature_min_c);
    const max = Number(row.temperature_max_c);
    const rain = Number(row.precipitation_total_mm || 0);
    const hasTemps = Number.isFinite(min) && Number.isFinite(max);
    const start = hasTemps ? ((min - globalMin) / globalRange) * 70 : 0;
    const span = hasTemps ? Math.max(8, ((max - min) / globalRange) * 70 + 8) : 0;
    return `<div class="daily-row" data-provider="${escapeHtml(provider)}">
      <span class="day-name">${escapeHtml(dayLabel(row.date))}</span>
      <span class="day-icon">${rainIcon(rain)}</span>
      <span class="temp-min">${hasTemps ? `${Math.round(min)}°` : "—"}</span>
      <span class="range-track"><span class="range-fill" style="left:${start.toFixed(1)}%;width:${Math.min(100 - start, span).toFixed(1)}%"></span></span>
      <span class="temp-max">${hasTemps ? `${Math.round(max)}°` : "—"}</span>
      <span class="rain-total">${rain.toFixed(1)} mm</span>
    </div>`;
  }).join("");

  const today = selected.find((row) => row.date === localDateKey()) || selected[0];
  if (today && Number.isFinite(Number(today.temperature_min_c)) && Number.isFinite(Number(today.temperature_max_c))) {
    qs("#heroHighLow").textContent = `H ${Math.round(Number(today.temperature_max_c))}° · L ${Math.round(Number(today.temperature_min_c))}° · ${modelName}`;
  }
}

function temperatureChart(series) {
  if (!series.length) return null;
  const primary = series.filter((item) => STAT_PREFERENCE.includes(item.statistic));
  const uncertaintyRows = series.filter((item) => item.provider === "weathernext3" && ["p10", "p90"].includes(item.statistic));
  const grouped = {};
  primary.forEach((item) => (grouped[item.provider] ??= []).push(item));
  const uncertaintyByTime = {};
  uncertaintyRows.forEach((item) => { (uncertaintyByTime[item.valid_time_utc] ??= {})[item.statistic] = Number(item.value); });
  const uncertainty = Object.entries(uncertaintyByTime).filter(([, values]) => values.p10 != null && values.p90 != null).sort(([a], [b]) => a.localeCompare(b));
  const allValues = primary.map((item) => Number(item.value));
  uncertainty.forEach(([, values]) => allValues.push(values.p10, values.p90));
  if (!allValues.length) return null;
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const range = Math.max(1, max - min);
  const times = [...new Set([...primary.map((item) => item.valid_time_utc), ...uncertainty.map(([time]) => time)])].sort();
  const x = (time) => 30 + (times.indexOf(time) / Math.max(1, times.length - 1)) * 570;
  const y = (value) => 190 - ((value - min) / range) * 150;
  let band = "";
  if (uncertainty.length >= 2) {
    const upper = uncertainty.map(([time, values]) => `${x(time).toFixed(1)},${y(values.p90).toFixed(1)}`);
    const lower = [...uncertainty].reverse().map(([time, values]) => `${x(time).toFixed(1)},${y(values.p10).toFixed(1)}`);
    band = `<polygon points="${[...upper, ...lower].join(" ")}" fill="rgba(56,189,248,.16)" stroke="rgba(56,189,248,.45)" stroke-width="1"/>`;
  }
  const paths = Object.entries(grouped).map(([name, providerRows], index) => {
    providerRows.sort((a, b) => a.valid_time_utc.localeCompare(b.valid_time_utc));
    const points = providerRows.map((row, rowIndex) => `${rowIndex ? "L" : "M"}${x(row.valid_time_utc).toFixed(1)},${y(Number(row.value)).toFixed(1)}`).join(" ");
    const hue = (index * 67) % 360;
    return `<path d="${points}" fill="none" stroke="hsl(${hue} 75% 65%)" stroke-width="2"/><text x="35" y="${18 + index * 14}" fill="hsl(${hue} 75% 70%)" font-size="10">${escapeHtml(name)}</text>`;
  }).join("");
  return `<svg viewBox="0 0 620 210" role="img" aria-label="48 hour temperature comparison with WeatherNext uncertainty band"><line x1="30" y1="190" x2="600" y2="190" stroke="#334155"/>${band}${paths}</svg>`;
}

function precipitationChart(series) {
  const rows = series.filter((item) => STAT_PREFERENCE.includes(item.statistic));
  if (!rows.length) return null;
  const providers = [...new Set(rows.map((item) => item.provider))];
  const times = [...new Set(rows.map((item) => item.valid_time_utc))].sort();
  const max = Math.max(0.1, ...rows.map((item) => Number(item.value)));
  const slot = 570 / Math.max(1, times.length);
  const providerWidth = Math.max(1.5, Math.min(8, (slot * 0.8) / Math.max(1, providers.length)));
  const bars = rows.map((row) => {
    const providerIndex = providers.indexOf(row.provider);
    const timeIndex = times.indexOf(row.valid_time_utc);
    const baseX = 30 + timeIndex * slot + slot * 0.1;
    const x = baseX + providerIndex * providerWidth;
    const height = Math.max(0, (Number(row.value) / max) * 145);
    const y = 180 - height;
    const hue = (providerIndex * 67) % 360;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${providerWidth.toFixed(1)}" height="${height.toFixed(1)}" fill="hsl(${hue} 70% 60%)"><title>${escapeHtml(row.provider)} ${escapeHtml(row.valid_time_utc)}: ${Number(row.value).toFixed(2)} mm</title></rect>`;
  }).join("");
  const legend = providers.map((provider, index) => `<text x="35" y="${16 + index * 13}" fill="hsl(${(index * 67) % 360} 75% 70%)" font-size="10">${escapeHtml(provider)}</text>`).join("");
  return `<svg viewBox="0 0 620 195" role="img" aria-label="48 hour precipitation comparison"><line x1="30" y1="180" x2="600" y2="180" stroke="#334155"/>${legend}${bars}</svg>`;
}

function uncertaintySummary(series) {
  const rows = series.filter((item) => item.provider === "weathernext3" && ["p10", "p90"].includes(item.statistic));
  if (!rows.length) return "WeatherNext uncertainty is unavailable until genuine provider data exists.";
  const byTime = {};
  rows.forEach((item) => { (byTime[item.valid_time_utc] ??= {})[item.statistic] = Number(item.value); });
  const complete = Object.entries(byTime).filter(([, values]) => values.p10 != null && values.p90 != null).slice(0, 12);
  if (!complete.length) return "WeatherNext p10–p90 pairs are incomplete.";
  return complete.map(([time, values]) => `${escapeHtml(time)}: ${values.p10.toFixed(1)}…${values.p90.toFixed(1)} °C`).join("<br>");
}

function renderTemperature(result, healthMap) {
  const rows = result.payload.series || [];
  const state = providerSurfaceState(rows, healthMap, result);
  setSurfaceState("modelsTempState", state.state, state.message);
  const tempSvg = temperatureChart(rows);
  if (tempSvg) {
    qs("#modelsChart").classList.remove("empty");
    qs("#modelsChart").innerHTML = tempSvg;
  } else {
    qs("#modelsChart").classList.add("empty");
    qs("#modelsChart").textContent = "No temperature forecasts are stored for this location.";
  }
  qs("#uncertainty").innerHTML = uncertaintySummary(rows);
}

function renderPrecipitation(result, healthMap) {
  const rows = result.payload.series || [];
  const state = providerSurfaceState(rows, healthMap, result);
  setSurfaceState("modelsPrecipState", state.state, state.message);
  const precipSvg = precipitationChart(rows);
  if (precipSvg) {
    qs("#modelsPrecip").classList.remove("empty");
    qs("#modelsPrecip").innerHTML = precipSvg;
  } else {
    qs("#modelsPrecip").classList.add("empty");
    qs("#modelsPrecip").textContent = "No precipitation forecasts are stored for this location.";
  }
}

function renderModelSnapshot(rows, healthMap) {
  const cards = MODEL_SNAPSHOT_IDS.map((provider) => {
    const series = futureRows(canonicalProviderRows(rows, provider), 1);
    const row = series[0];
    const health = healthMap[provider];
    const healthState = health?.state || health?.freshness_state || (provider === "weathernext3" ? "access_pending" : "unknown");
    const value = row && Number.isFinite(Number(row.value)) ? `${Number(row.value).toFixed(1)}°` : "—";
    const note = row ? `${formatLocalTime(row.valid_time_utc)} · ${row.statistic}` : (provider === "weathernext3" ? "No genuine data · pending" : healthState);
    return `<div class="model-card ${provider === "weathernext3" ? "primary" : ""}" data-provider="${provider}">
      <small>${escapeHtml(MODEL_LABELS[provider])}</small>
      <strong>${value}</strong>
      <span ${provider === "weathernext3" ? 'id="wnState"' : ""}>${escapeHtml(note)}</span>
    </div>`;
  });
  qs("#modelSnapshot").innerHTML = cards.join("");
  const values = MODEL_SNAPSHOT_IDS.map((provider) => futureRows(canonicalProviderRows(rows, provider), 1)[0]).filter(Boolean).map((row) => Number(row.value)).filter(Number.isFinite);
  qs("#modelSpread").textContent = values.length >= 2 ? `Model spread ${(Math.max(...values) - Math.min(...values)).toFixed(1)}° · descriptive provider disagreement` : "Model spread — · waiting for at least two genuine model values";
}

async function refresh() {
  const sequence = ++refreshSequence;
  let healthResult;
  try {
    healthResult = await apiWithFallback("/api/health/providers", "provider-health");
    if (sequence !== refreshSequence) return;
    lastHealth = healthResult.payload;
    if (!forecastLocationInitialized) {
      qs("#forecastLocation").value = lastHealth.home.configured ? "home" : "station_05480";
      forecastLocationInitialized = true;
    }
    qs("#providerGrid").innerHTML = providersCard(lastHealth.providers);
    qs("#providerClasses").innerHTML = providersCard(lastHealth.providers);
    const healthState = providerGridState(lastHealth, healthResult);
    setSurfaceState("providerState", healthState.state, healthState.message);
    globalNetworkState(healthState);
  } catch (error) {
    if (sequence !== refreshSequence) return;
    lastHealth = null;
    setSurfaceState("providerState", navigator.onLine ? "error" : "offline", `Provider health unavailable: ${error}`, { alert: true });
    globalNetworkState({ state: navigator.onLine ? "error" : "offline", message: "Provider health API unavailable." });
  }

  if (sequence !== refreshSequence) return;
  const locationId = qs("#forecastLocation").value;
  const locationMeta = FORECAST_LOCATION_META[locationId] || FORECAST_LOCATION_META.station_05480;
  qsa(".forecast-location-label").forEach((node) => { node.textContent = locationMeta.label; });
  qs("#forecastLocationNote").textContent = locationMeta.note;
  qs("#heroLocation").textContent = locationMeta.heroLabel;
  const healthMap = providerHealthMap(lastHealth);

  const requests = await Promise.allSettled([
    apiWithFallback("/api/current", "current"),
    apiWithFallback(`/api/hourly?hours=48&variable=temperature_2m&location_id=${locationId}`, `hourly-temperature-48-${locationId}`),
    apiWithFallback(`/api/hourly?hours=48&variable=precipitation_1h&location_id=${locationId}`, `hourly-precipitation-48-${locationId}`),
    apiWithFallback(`/api/daily?days=10&location_id=${locationId}`, `daily-10-${locationId}`),
  ]);
  if (sequence !== refreshSequence) return;
  const [current, temperature, precipitation, daily] = requests;

  if (current.status === "fulfilled") renderCurrent(current.value, healthMap);
  else {
    qs("#heroUpdated").textContent = "Current observation unavailable";
    qs("#heroTemperature").textContent = "—°";
    qs("#heroCondition").textContent = "Observation unavailable";
    setSurfaceState("currentState", navigator.onLine ? "error" : "offline", `DWD current observation unavailable: ${current.reason}`, { alert: true });
  }

  if (temperature.status === "fulfilled") {
    renderTemperature(temperature.value, healthMap);
    renderModelSnapshot(temperature.value.payload.series || [], healthMap);
  } else {
    setSurfaceState("modelsTempState", navigator.onLine ? "error" : "offline", `Temperature forecast unavailable: ${temperature.reason}`, { alert: true });
    setSurfaceState("overviewTempState", navigator.onLine ? "error" : "offline", `Temperature forecast unavailable: ${temperature.reason}`, { alert: true });
  }

  if (precipitation.status === "fulfilled") renderPrecipitation(precipitation.value, healthMap);
  else {
    setSurfaceState("modelsPrecipState", navigator.onLine ? "error" : "offline", `Precipitation forecast unavailable: ${precipitation.reason}`, { alert: true });
    setSurfaceState("overviewPrecipState", navigator.onLine ? "error" : "offline", `Precipitation forecast unavailable: ${precipitation.reason}`, { alert: true });
  }

  if (temperature.status === "fulfilled" && precipitation.status === "fulfilled") renderConsumerHourly(temperature.value, precipitation.value, healthMap);
  else {
    qs("#hourlyStrip").innerHTML = '<div class="empty-card">Next-hours forecast unavailable.</div>';
    qs("#consumerHourlyChart").innerHTML = "";
  }

  if (daily.status === "fulfilled") renderDaily(daily.value, healthMap);
  else {
    qs("#dailyGrid").textContent = "Daily forecast unavailable.";
    setSurfaceState("dailyState", navigator.onLine ? "error" : "offline", `Daily forecast unavailable: ${daily.reason}`, { alert: true });
  }
}

async function accuracy(days = 30) {
  try {
    const data = (await apiWithFallback(`/api/verification/summary?days=${days}`, `verification-summary-${days}`)).payload;
    const rows = data.common_sample_slices || [];
    if (!rows.length) {
      qs("#accuracyTable").textContent = "Not enough common station samples exist between at least two providers in one lead-bucket/model-version cohort.";
      return;
    }
    qs("#accuracyTable").innerHTML = `<table><thead><tr><th>Model</th><th>Version</th><th>Lead</th><th>n</th><th>Missing</th><th>Sufficiency</th><th>MAE</th><th>RMSE</th><th>Bias</th><th>p10–p90</th></tr></thead><tbody>${rows.map((metrics) => {
      const missing = metrics.missingness || {};
      return `<tr><td>${escapeHtml(metrics.provider)}</td><td>${escapeHtml(metrics.model_version || "unknown")}</td><td>${escapeHtml(metrics.lead_bucket)}</td><td>${metrics.n}</td><td>${missing.missing_n ?? "—"}/${missing.expected_n ?? "—"}</td><td>${escapeHtml(metrics.sample_sufficiency_state)}</td><td>${metrics.mae?.toFixed(2) ?? "—"}</td><td>${metrics.rmse?.toFixed(2) ?? "—"}</td><td>${metrics.bias?.toFixed(2) ?? "—"}</td><td>${metrics.p10_p90_coverage == null ? "—" : `${(metrics.p10_p90_coverage * 100).toFixed(0)}% (${metrics.coverage_n})`}</td></tr>`;
    }).join("")}</tbody></table>`;
  } catch (_error) {
    qs("#accuracyTable").textContent = "Accuracy API unavailable";
  }
}

qsa("[data-days]").forEach((button) => {
  button.onclick = () => {
    qsa("[data-days]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    accuracy(Number(button.dataset.days));
  };
});

function updateOverviewWarning(result) {
  if (stateFromResult(result) !== "fresh") {
    qs("#overviewWarningState").textContent = "Cached warning response · not current official status";
    return;
  }
  const payload = result.payload || {};
  if (payload.state === "no_active_alerts") {
    qs("#overviewWarningState").textContent = "No active warnings · current DWD response";
    return;
  }
  const active = (payload.alerts || []).filter((alert) => alert.lifecycle !== "expired");
  qs("#overviewWarningState").textContent = active.length ? `${active.length} DWD warning${active.length === 1 ? "" : "s"} · open details` : "DWD warning response loaded";
}

async function loadSafetySurface(kind) {
  const isWarning = kind === "warnings";
  const url = isWarning ? "/api/warnings" : "/api/radar";
  const stateId = isWarning ? "warningsState" : "radarState";
  const outputId = isWarning ? "warningsOutput" : "radarOutput";
  loadedSafetySurfaces.add(kind);
  try {
    const result = await apiWithFallback(url, `safety-${kind}`);
    qs(`#${outputId}`).textContent = JSON.stringify(result.payload, null, 2);
    const fallbackState = stateFromResult(result);
    if (fallbackState === "fresh") {
      setSurfaceState(stateId, "fresh", isWarning ? "Current response from the DWD official-warning endpoint." : "Current DWD radar metadata response.");
      if (isWarning) updateOverviewWarning(result);
    } else if (isWarning) {
      setSurfaceState(stateId, fallbackState, `${cacheMessage(result)} — NOT current official warning status. DWD remains the authority; reconnect and refresh before relying on warnings.`, { alert: true });
      updateOverviewWarning(result);
    } else {
      setSurfaceState(stateId, fallbackState, `${cacheMessage(result)} — cached radar metadata is not current observed/nowcast evidence.`);
    }
  } catch (error) {
    qs(`#${outputId}`).textContent = isWarning ? "Current DWD warning data nav pieejama." : "Current DWD radar data nav pieejama.";
    setSurfaceState(stateId, navigator.onLine ? "error" : "offline", `${isWarning ? "DWD official warning" : "DWD radar"} endpoint unavailable: ${error}`, { alert: isWarning });
    if (isWarning) qs("#overviewWarningState").textContent = "Current DWD warning status unavailable";
  }
}

qs("#forecastLocation").onchange = () => { forecastLocationInitialized = true; refresh(); };
qs("#refreshOverview").onclick = () => refresh();
qs("#loadWarnings").onclick = () => loadSafetySurface("warnings");
qs("#loadRadar").onclick = () => loadSafetySurface("radar");
qs("#overviewWarningsButton").onclick = () => {
  setActiveView("safety");
  if (!loadedSafetySurfaces.has("warnings")) loadSafetySurface("warnings");
};

window.addEventListener("offline", () => {
  setSurfaceState("networkState", "offline", "Browser reports offline. Visible forecast data is last-known cache and is not current.", { alert: true });
  ["currentState", "overviewTempState", "overviewPrecipState", "dailyState", "modelsTempState", "modelsPrecipState", "providerState"].forEach((id) => {
    const element = qs(`#${id}`);
    if (element && element.dataset.state === "fresh") setSurfaceState(id, "offline", "Connection lost. Previously rendered data must be treated as last-known, not current.");
  });
  if (loadedSafetySurfaces.has("warnings")) setSurfaceState("warningsState", "offline", "Connection lost — displayed DWD warning data is NOT current official warning status.", { alert: true });
  if (loadedSafetySurfaces.has("radar")) setSurfaceState("radarState", "offline", "Connection lost — displayed radar metadata is not current.");
});

window.addEventListener("online", () => {
  setSurfaceState("networkState", "loading", "Connection returned; refreshing live API evidence.");
  refresh();
  loadedSafetySurfaces.forEach((kind) => loadSafetySurface(kind));
});

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/static/sw.js");
refresh();
