const qs = (selector) => document.querySelector(selector);
const qsa = (selector) => [...document.querySelectorAll(selector)];

const DATA_CACHE_PREFIX = "rozkalns-weather:pwa-cache:v1:";
const UI_STATES = ["loading", "fresh", "stale", "error", "offline"];
const PUBLIC_PROVIDER_IDS = new Set(["dwd_observations", "dwd_mosmix_l", "icon_d2", "ecmwf_ifs", "ecmwf_aifs"]);
const loadedSafetySurfaces = new Set();
let lastHealth = null;

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

function formatTimestamp(value) {
  if (!value) return "unknown time";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString([], { dateStyle: "short", timeStyle: "short" });
}

function cacheMessage(result) {
  return `cached ${formatTimestamp(result.cached_at_utc)}`;
}

function normalizedProviderState(provider) {
  const freshness = provider?.freshness_state || "unknown";
  if (freshness === "fresh") return "fresh";
  if (freshness === "error") return "error";
  if (["lagging", "degraded", "stale", "unknown", "not_ingested"].includes(freshness)) return "stale";
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
  if (degraded.length === providers.length) {
    return {
      state: "error",
      message: `All displayed providers are degraded (${degraded.join(", ")}); latest retrieval ${formatTimestamp(latestRetrieved)}.`,
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
  if (degraded.length === tracked.length) return { state: "error", message: "All recurring public providers are degraded or not yet fresh." };
  return { state: "stale", message: `Partial provider degradation: ${degraded.map((provider) => provider.id).join(", ")}. Healthy providers remain visible.` };
}

function globalNetworkState(healthState) {
  if (!navigator.onLine) {
    setSurfaceState("networkState", "offline", "Browser reports offline. Last-known data is shown only when a visible cache timestamp is available.", { alert: true });
    return;
  }
  setSurfaceState("networkState", healthState.state, healthState.message, { alert: healthState.state === "error" });
}

qsa(".tabs button").forEach((button) => {
  button.onclick = () => {
    qsa(".tabs button").forEach((item) => item.classList.remove("active"));
    qsa(".view").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    qs(`#${button.dataset.view}`).classList.add("active");
  };
});

function providersCard(items) {
  return items.map((provider) => {
    const uiState = normalizedProviderState(provider);
    return `
    <div class="provider provider-state-${uiState}">
      <div class="provider-heading"><strong>${provider.model_name}</strong><span class="state-chip state-${uiState}">${uiState}</span></div>
      <small>
        ingest ${provider.ingest_state || provider.state}
        <br>freshness ${provider.freshness_state || "unknown"}
        ${provider.failure_domain && provider.failure_domain !== "none" ? `<br>domain ${provider.failure_domain}` : ""}
        ${provider.reason_code ? `<br>${provider.reason_code}` : ""}
        ${provider.last_init_time_utc ? `<br>init ${provider.last_init_time_utc}` : ""}
        ${provider.last_retrieved_at_utc ? `<br>retrieved ${provider.last_retrieved_at_utc}` : ""}
        ${provider.latest_valid_time_utc ? `<br>valid through ${provider.latest_valid_time_utc}` : ""}
        ${provider.last_observed_at_utc ? `<br>observed ${provider.last_observed_at_utc}` : ""}
        ${provider.last_success_at_utc ? `<br>success ${provider.last_success_at_utc}` : ""}
      </small>
    </div>
  `;
  }).join("");
}

function currentCards(items) {
  return items.map((item) => `
    <div class="provider">
      <strong>${item.variable}</strong>
      <small>${Number(item.value).toFixed(1)} ${item.unit}<br>DWD observed ${item.observed_at_utc}</small>
    </div>
  `).join("");
}

function dailyCards(items, healthMap) {
  return items.slice(0, 40).map((item) => {
    const uiState = normalizedProviderState(healthMap[item.provider]);
    return `
    <div class="provider provider-state-${uiState}">
      <div class="provider-heading"><strong>${item.date} · ${item.model_name}</strong><span class="state-chip state-${uiState}">${uiState}</span></div>
      <small>
        ${item.temperature_min_c == null ? "—" : Number(item.temperature_min_c).toFixed(1)}
        …
        ${item.temperature_max_c == null ? "—" : Number(item.temperature_max_c).toFixed(1)} °C
        <br>${Number(item.precipitation_total_mm || 0).toFixed(1)} mm
        <br>init ${item.init_time_utc || "—"}
        <br>retrieved ${item.retrieved_at_utc || "—"}
      </small>
    </div>
  `;
  }).join("");
}

function temperatureChart(series) {
  if (!series.length) return null;
  const primary = series.filter((item) => ["deterministic", "mean", "p50"].includes(item.statistic));
  const uncertaintyRows = series.filter((item) => item.provider === "weathernext3" && ["p10", "p90"].includes(item.statistic));
  const grouped = {};
  primary.forEach((item) => (grouped[item.provider] ??= []).push(item));
  const uncertaintyByTime = {};
  uncertaintyRows.forEach((item) => {
    (uncertaintyByTime[item.valid_time_utc] ??= {})[item.statistic] = Number(item.value);
  });
  const uncertainty = Object.entries(uncertaintyByTime)
    .filter(([, values]) => values.p10 != null && values.p90 != null)
    .sort(([a], [b]) => a.localeCompare(b));
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
  const paths = Object.entries(grouped).map(([name, rows], index) => {
    rows.sort((a, b) => a.valid_time_utc.localeCompare(b.valid_time_utc));
    const points = rows.map((row, rowIndex) => `${rowIndex ? "L" : "M"}${x(row.valid_time_utc).toFixed(1)},${y(Number(row.value)).toFixed(1)}`).join(" ");
    const hue = (index * 67) % 360;
    return `<path d="${points}" fill="none" stroke="hsl(${hue} 75% 65%)" stroke-width="2"/><text x="35" y="${18 + index * 14}" fill="hsl(${hue} 75% 70%)" font-size="10">${name}</text>`;
  }).join("");
  return `<svg viewBox="0 0 620 210" role="img" aria-label="48 hour temperature comparison with WeatherNext uncertainty band"><line x1="30" y1="190" x2="600" y2="190" stroke="#334155"/>${band}${paths}</svg>`;
}

function precipitationChart(series) {
  const rows = series.filter((item) => ["deterministic", "mean", "p50"].includes(item.statistic));
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
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${providerWidth.toFixed(1)}" height="${height.toFixed(1)}" fill="hsl(${hue} 70% 60%)"><title>${row.provider} ${row.valid_time_utc}: ${Number(row.value).toFixed(2)} mm</title></rect>`;
  }).join("");
  const legend = providers.map((provider, index) => `<text x="35" y="${16 + index * 13}" fill="hsl(${(index * 67) % 360} 75% 70%)" font-size="10">${provider}</text>`).join("");
  return `<svg viewBox="0 0 620 195" role="img" aria-label="48 hour precipitation comparison"><line x1="30" y1="180" x2="600" y2="180" stroke="#334155"/>${legend}${bars}</svg>`;
}

function uncertaintySummary(series) {
  const rows = series.filter((item) => item.provider === "weathernext3" && ["p10", "p90"].includes(item.statistic));
  if (!rows.length) return "WeatherNext uncertainty vēl nav pieejama.";
  const byTime = {};
  rows.forEach((item) => (byTime[item.valid_time_utc] ??= {})[item.statistic] = Number(item.value));
  const complete = Object.entries(byTime).filter(([, values]) => values.p10 != null && values.p90 != null).slice(0, 12);
  if (!complete.length) return "WeatherNext p10–p90 pāri vēl nav pilni.";
  return complete.map(([time, values]) => `${time}: ${values.p10.toFixed(1)}…${values.p90.toFixed(1)} °C`).join("<br>");
}

function renderCurrent(result, healthMap) {
  const current = result.payload;
  if (current.observations?.length) qs("#currentTruth").innerHTML = currentCards(current.observations);
  else qs("#currentTruth").textContent = "Nav observation datu.";
  const fallbackState = stateFromResult(result);
  const observed = (current.observations || []).map((item) => item.observed_at_utc).filter(Boolean).sort().at(-1) || null;
  if (fallbackState !== "fresh") {
    setSurfaceState("currentState", fallbackState, `${cacheMessage(result)}; DWD observation ${formatTimestamp(observed)}. This is not current live evidence.`);
    return;
  }
  const dwdState = normalizedProviderState(healthMap.dwd_observations);
  if (!current.observations?.length) setSurfaceState("currentState", "stale", "No stored DWD WMO 10416 observation is available yet.");
  else if (dwdState === "fresh") setSurfaceState("currentState", "fresh", `DWD WMO 10416 observation ${formatTimestamp(observed)}.`);
  else setSurfaceState("currentState", dwdState === "error" ? "error" : "stale", `DWD observation ${formatTimestamp(observed)}; provider health is ${healthMap.dwd_observations?.freshness_state || "unknown"}.`);
}

function renderTemperature(result, healthMap) {
  const rows = result.payload.series || [];
  const state = providerSurfaceState(rows, healthMap, result);
  ["overviewTempState", "modelsTempState"].forEach((id) => setSurfaceState(id, state.state, state.message));
  const tempSvg = temperatureChart(rows);
  if (tempSvg) {
    ["overviewChart", "modelsChart"].forEach((id) => {
      qs(`#${id}`).classList.remove("empty");
      qs(`#${id}`).innerHTML = tempSvg;
    });
  }
  qs("#uncertainty").innerHTML = uncertaintySummary(rows);
}

function renderPrecipitation(result, healthMap) {
  const rows = result.payload.series || [];
  const state = providerSurfaceState(rows, healthMap, result);
  ["overviewPrecipState", "modelsPrecipState"].forEach((id) => setSurfaceState(id, state.state, state.message));
  const precipSvg = precipitationChart(rows);
  if (precipSvg) {
    ["overviewPrecip", "modelsPrecip"].forEach((id) => {
      qs(`#${id}`).classList.remove("empty");
      qs(`#${id}`).innerHTML = precipSvg;
    });
  }
}

function renderDaily(result, healthMap) {
  const rows = result.payload.days_by_provider || [];
  const state = providerSurfaceState(rows, healthMap, result);
  setSurfaceState("dailyState", state.state, state.message);
  qs("#dailyGrid").innerHTML = rows.length ? dailyCards(rows, healthMap) : "Nav datu.";
}

async function refresh() {
  let healthResult;
  try {
    healthResult = await apiWithFallback("/api/health/providers", "provider-health");
    lastHealth = healthResult.payload;
    qs("#statusBadge").textContent = lastHealth.home.configured ? "home configured" : "home config pending";
    qs("#providerGrid").innerHTML = providersCard(lastHealth.providers);
    const healthState = providerGridState(lastHealth, healthResult);
    setSurfaceState("providerState", healthState.state, healthState.message);
    globalNetworkState(healthState);
    const weatherNext = lastHealth.providers.find((item) => item.id === "weathernext3");
    qs("#wnState").textContent = weatherNext?.state || "unknown";
  } catch (error) {
    lastHealth = null;
    qs("#statusBadge").textContent = navigator.onLine ? "API unavailable" : "offline";
    setSurfaceState("providerState", navigator.onLine ? "error" : "offline", `Provider health unavailable: ${error}`, { alert: true });
    globalNetworkState({ state: navigator.onLine ? "error" : "offline", message: "Provider health API unavailable." });
  }

  const healthMap = providerHealthMap(lastHealth);
  const requests = await Promise.allSettled([
    apiWithFallback("/api/current", "current"),
    apiWithFallback("/api/hourly?hours=48&variable=temperature_2m", "hourly-temperature-48"),
    apiWithFallback("/api/hourly?hours=48&variable=precipitation_1h", "hourly-precipitation-48"),
    apiWithFallback("/api/daily?days=10", "daily-10"),
  ]);
  const [current, temperature, precipitation, daily] = requests;
  if (current.status === "fulfilled") renderCurrent(current.value, healthMap);
  else setSurfaceState("currentState", navigator.onLine ? "error" : "offline", `DWD current observation unavailable: ${current.reason}`, { alert: true });
  if (temperature.status === "fulfilled") renderTemperature(temperature.value, healthMap);
  else ["overviewTempState", "modelsTempState"].forEach((id) => setSurfaceState(id, navigator.onLine ? "error" : "offline", `Temperature forecast unavailable: ${temperature.reason}`, { alert: true }));
  if (precipitation.status === "fulfilled") renderPrecipitation(precipitation.value, healthMap);
  else ["overviewPrecipState", "modelsPrecipState"].forEach((id) => setSurfaceState(id, navigator.onLine ? "error" : "offline", `Precipitation forecast unavailable: ${precipitation.reason}`, { alert: true }));
  if (daily.status === "fulfilled") renderDaily(daily.value, healthMap);
  else setSurfaceState("dailyState", navigator.onLine ? "error" : "offline", `Daily forecast unavailable: ${daily.reason}`, { alert: true });
}

async function accuracy(days = 30) {
  try {
    const data = (await apiWithFallback(`/api/verification/summary?days=${days}`, `verification-summary-${days}`)).payload;
    const rows = data.common_sample_slices || [];
    if (!rows.length) {
      qs("#accuracyTable").textContent = "Vēl nav pietiekamu kopīgu station sample starp vismaz diviem provider vienā lead bucket/model-version cohort.";
      return;
    }
    qs("#accuracyTable").innerHTML = `<table><thead><tr><th>Model</th><th>Version</th><th>Lead</th><th>n</th><th>Missing</th><th>Sufficiency</th><th>MAE</th><th>RMSE</th><th>Bias</th><th>p10–p90</th></tr></thead><tbody>${rows.map((metrics) => {
      const missing = metrics.missingness || {};
      return `<tr><td>${metrics.provider}</td><td>${metrics.model_version || "unknown"}</td><td>${metrics.lead_bucket}</td><td>${metrics.n}</td><td>${missing.missing_n ?? "—"}/${missing.expected_n ?? "—"}</td><td>${metrics.sample_sufficiency_state}</td><td>${metrics.mae?.toFixed(2) ?? "—"}</td><td>${metrics.rmse?.toFixed(2) ?? "—"}</td><td>${metrics.bias?.toFixed(2) ?? "—"}</td><td>${metrics.p10_p90_coverage == null ? "—" : `${(metrics.p10_p90_coverage * 100).toFixed(0)}% (${metrics.coverage_n})`}</td></tr>`;
    }).join("")}</tbody></table>`;
  } catch (error) {
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
    } else if (isWarning) {
      setSurfaceState(stateId, fallbackState, `${cacheMessage(result)} — NOT current official warning status. DWD remains the authority; reconnect and refresh before relying on warnings.`, { alert: true });
    } else {
      setSurfaceState(stateId, fallbackState, `${cacheMessage(result)} — cached radar metadata is not current observed/nowcast evidence.`);
    }
  } catch (error) {
    qs(`#${outputId}`).textContent = isWarning ? "Current DWD warning data nav pieejama." : "Current DWD radar data nav pieejama.";
    setSurfaceState(stateId, navigator.onLine ? "error" : "offline", `${isWarning ? "DWD official warning" : "DWD radar"} endpoint unavailable: ${error}`, { alert: isWarning });
  }
}

qs("#loadWarnings").onclick = () => loadSafetySurface("warnings");
qs("#loadRadar").onclick = () => loadSafetySurface("radar");

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
accuracy(30);
