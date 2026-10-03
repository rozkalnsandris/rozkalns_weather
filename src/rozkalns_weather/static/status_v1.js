(function (root) {
  "use strict";

  const PUBLIC_ORDER = ["dwd_observations", "icon_d2", "ecmwf_ifs", "ecmwf_aifs"];
  let requestSequence = 0;

  function qs(selector) {
    return root.document?.querySelector(selector) || null;
  }

  function escapeHtml(value) {
    if (typeof root.escapeHtml === "function") return root.escapeHtml(value);
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function finiteNumber(value) {
    const parsed = Number(value);
    return value == null || value === "" || !Number.isFinite(parsed) ? null : parsed;
  }

  function providerState(provider) {
    if (typeof root.normalizedProviderState === "function") return root.normalizedProviderState(provider);
    const states = [provider?.state, provider?.ingest_state, provider?.freshness_state];
    if (states.includes("error")) return "error";
    if (provider?.freshness_state === "fresh") return "fresh";
    return "stale";
  }

  function stateFromResult(result) {
    if (typeof root.stateFromResult === "function") return root.stateFromResult(result);
    if (result?.source === "offline-cache") return "offline";
    if (result?.source === "stale-cache") return "stale";
    return result ? "fresh" : "error";
  }

  function formatTimestamp(value) {
    if (typeof root.formatTimestamp === "function") return root.formatTimestamp(value);
    return value || "unknown time";
  }

  function providerSummary(provider) {
    const retrieved = provider?.last_retrieved_at_utc ? `retrieved ${formatTimestamp(provider.last_retrieved_at_utc)}` : "no retrieval timestamp";
    const freshness = provider?.freshness_state || "unknown";
    return `${freshness} · ${retrieved}`;
  }

  function renderSources(health) {
    const target = qs("#statusSources");
    if (!target) return;
    const byId = Object.fromEntries((health?.providers || []).map((provider) => [provider.id, provider]));
    const providers = PUBLIC_ORDER.map((id) => byId[id]).filter(Boolean);
    if (!providers.length) {
      target.textContent = "Public provider status evidence is unavailable.";
      return;
    }
    target.innerHTML = providers.map((provider) => {
      const state = providerState(provider);
      const technical = [
        `ingest ${provider.ingest_state || provider.state || "unknown"}`,
        `freshness ${provider.freshness_state || "unknown"}`,
        provider.failure_domain && provider.failure_domain !== "none" ? `domain ${provider.failure_domain}` : null,
        provider.reason_code ? `reason ${provider.reason_code}` : null,
        provider.last_init_time_utc ? `init ${provider.last_init_time_utc}` : null,
        provider.last_retrieved_at_utc ? `retrieved ${provider.last_retrieved_at_utc}` : null,
      ].filter(Boolean);
      return `<article class="status-source-row provider-state-${escapeHtml(state)}">
        <div class="status-source-heading"><strong>${escapeHtml(provider.model_name || provider.id)}</strong><span class="state-chip state-${escapeHtml(state)}">${escapeHtml(state)}</span></div>
        <div class="status-source-summary">${escapeHtml(providerSummary(provider))}</div>
        <details class="status-source-details"><summary>Technical details</summary><div>${technical.map((line) => escapeHtml(line)).join("<br>")}</div></details>
      </article>`;
    }).join("");
  }

  function verificationReadiness(summary) {
    if (!summary || typeof summary !== "object") {
      return { state: "error", label: "Unavailable", detail: "Verification response is unavailable." };
    }
    if (summary.verification_ready !== true) {
      const reasons = summary.truth_quality?.reason_codes || [];
      return {
        state: "stale",
        label: "Not ready · benchmark truth incomplete",
        detail: reasons.length ? `Truth-quality reasons: ${reasons.join(", ")}.` : "Benchmark truth-quality checks are incomplete.",
      };
    }
    const overall = summary.providers?.weathernext3?.overall;
    const n = Number(overall?.n || 0);
    if (!(n > 0)) {
      return {
        state: "stale",
        label: "Not ready · no WeatherNext verified samples",
        detail: "Benchmark truth is ready, but no genuine WeatherNext verification samples exist in this window.",
      };
    }
    const cohorts = (summary.common_sample_slices || []).filter((row) => row?.provider === "weathernext3");
    const sufficient = cohorts.filter((row) => row.sample_sufficiency_state === "sufficient");
    if (!sufficient.length) {
      return {
        state: "stale",
        label: `Not ready · n=${n}; common sample insufficient`,
        detail: "WeatherNext samples exist, but no common-sample cohort is sufficient for the comparison surface.",
      };
    }
    return {
      state: "fresh",
      label: `Ready · ${sufficient.length} sufficient cohort${sufficient.length === 1 ? "" : "s"}`,
      detail: `WeatherNext has n=${n} descriptive samples; detailed common-sample evidence remains on Accuracy.`,
    };
  }

  function forecastAvailability(result, health) {
    const fallback = stateFromResult(result);
    const rows = result?.payload?.series || [];
    const row = rows.find((item) => item?.provider === "weathernext3" && finiteNumber(item?.value) != null) || null;
    const healthStates = [health?.ingest_state, health?.state, health?.freshness_state];
    if (row) {
      const state = fallback === "fresh" && !healthStates.includes("error") ? "fresh" : (fallback === "offline" ? "offline" : "stale");
      const value = finiteNumber(row.value);
      const provenance = [
        `valid ${row.valid_time_utc || "unknown"}`,
        row.init_time_utc ? `init ${row.init_time_utc}` : "init unknown",
        row.lead_hours == null ? "lead unknown" : `lead ${row.lead_hours} h`,
        row.retrieved_at_utc ? `retrieved ${row.retrieved_at_utc}` : "retrieved unknown",
        `statistic ${row.statistic || "unknown"}`,
        `model version ${row.model_version || "unknown"}`,
      ].join(" · ");
      return { state, label: `Available · ${value.toFixed(1)}°`, detail: provenance };
    }
    if (healthStates.includes("error")) {
      return { state: "error", label: "Unavailable · provider error", detail: `Provider state ${health?.reason_code || health?.freshness_state || health?.state || "error"}.` };
    }
    if (healthStates.includes("access_pending")) {
      return { state: "pending", label: "No genuine data · access pending", detail: "No WeatherNext value is inferred from another provider." };
    }
    if (fallback === "offline") {
      return { state: "offline", label: "No genuine WeatherNext forecast available", detail: "No WeatherNext value is inferred from another provider." };
    }
    if (fallback === "stale") {
      return { state: "stale", label: "No genuine WeatherNext forecast available", detail: "Cached forecast availability evidence is stale; no WeatherNext value is inferred from another provider." };
    }
    return {
      state: "pending",
      label: "No genuine WeatherNext forecast available · pending",
      detail: "No WeatherNext value is inferred from another provider.",
    };
  }

  function renderWeatherNext(forecast, verification) {
    const card = qs("#statusWeatherNext");
    const state = qs("#statusWeatherNextState");
    const forecastValue = qs("#statusWeatherNextForecast");
    const forecastMeta = qs("#statusWeatherNextForecastMeta");
    const verificationValue = qs("#statusWeatherNextVerification");
    const verificationMeta = qs("#statusWeatherNextVerificationMeta");
    if (!card || !state || !forecastValue || !forecastMeta || !verificationValue || !verificationMeta) return;

    const combined = forecast.state === "error" || verification.state === "error"
      ? "error"
      : forecast.state === "offline" || verification.state === "offline"
        ? "offline"
        : forecast.state === "pending"
          ? "pending"
          : forecast.state === "fresh" && verification.state === "fresh"
            ? "fresh"
            : "stale";
    card.dataset.state = combined;
    state.className = `surface-state state-${combined}`;
    state.dataset.state = combined;
    state.textContent = `${combined.toUpperCase()} · forecast availability and verification readiness are reported separately`;
    forecastValue.textContent = forecast.label;
    forecastMeta.textContent = forecast.detail;
    verificationValue.textContent = verification.label;
    verificationMeta.textContent = verification.detail;
  }

  function setLoading() {
    const card = qs("#statusWeatherNext");
    if (card) card.dataset.state = "loading";
    const state = qs("#statusWeatherNextState");
    if (state) {
      state.className = "surface-state state-loading";
      state.dataset.state = "loading";
      state.textContent = "LOADING · checking WeatherNext forecast availability and verification readiness";
    }
    const sources = qs("#statusSources");
    if (sources) sources.textContent = "Loading independent public-provider status…";
  }

  async function api(url, cacheKey) {
    if (typeof root.apiWithFallback === "function") return root.apiWithFallback(url, cacheKey);
    const response = await root.fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return { payload: await response.json(), source: "network", cached_at_utc: new Date().toISOString(), error: null };
  }

  async function load() {
    const sequence = ++requestSequence;
    setLoading();
    const locationId = qs("#forecastLocation")?.value || "station_05480";
    const requests = await Promise.allSettled([
      api("/api/health/providers", "status-provider-health"),
      api(`/api/hourly?hours=48&variable=temperature_2m&location_id=${encodeURIComponent(locationId)}&providers=weathernext3`, `status-weathernext-${locationId}`),
      api("/api/verification/summary?days=30", "status-verification-summary-30"),
    ]);
    if (sequence !== requestSequence) return;

    const [healthResult, forecastResult, verificationResult] = requests;
    const healthPayload = healthResult.status === "fulfilled" ? healthResult.value.payload : null;
    if (healthPayload) renderSources(healthPayload);
    else {
      const sources = qs("#statusSources");
      if (sources) sources.textContent = `Public provider status unavailable: ${healthResult.reason}`;
    }

    const health = healthPayload?.providers?.find((provider) => provider.id === "weathernext3") || {};
    const forecast = forecastResult.status === "fulfilled"
      ? forecastAvailability(forecastResult.value, health)
      : { state: root.navigator?.onLine === false ? "offline" : "error", label: "Forecast availability unavailable", detail: String(forecastResult.reason || "request failed") };
    const verification = verificationResult.status === "fulfilled"
      ? verificationReadiness(verificationResult.value.payload)
      : { state: root.navigator?.onLine === false ? "offline" : "error", label: "Verification readiness unavailable", detail: String(verificationResult.reason || "request failed") };
    renderWeatherNext(forecast, verification);
  }

  function install() {
    qs("#forecastLocation")?.addEventListener("change", () => {
      if (qs("#status")?.classList.contains("active")) void load();
    });
    root.addEventListener?.("online", () => {
      if (qs("#status")?.classList.contains("active")) void load();
    });
    root.addEventListener?.("offline", () => {
      const card = qs("#statusWeatherNext");
      if (card) card.dataset.state = "offline";
      const state = qs("#statusWeatherNextState");
      if (!state) return;
      state.className = "surface-state state-offline";
      state.dataset.state = "offline";
      state.textContent = "OFFLINE · displayed Status evidence is last-known and not current";
    });
  }

  root.rozkalnsStatus = {
    forecastAvailability,
    verificationReadiness,
    renderSources,
    load,
  };
  if (root.document) install();
})(typeof window !== "undefined" ? window : globalThis);
