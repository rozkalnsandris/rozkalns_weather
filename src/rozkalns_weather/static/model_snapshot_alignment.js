/* Model Snapshot compares provider values only at one exact shared valid time. */
(function (root) {
  "use strict";

  const PROVIDERS = ["weathernext3", "icon_d2", "ecmwf_ifs", "ecmwf_aifs"];
  const LABELS = Object.freeze({
    weathernext3: "WeatherNext 3",
    icon_d2: "ICON-D2",
    ecmwf_ifs: "ECMWF IFS",
    ecmwf_aifs: "AIFS",
  });
  const GRACE_MS = 30 * 60 * 1000;

  function finiteNumber(value) {
    const parsed = Number(value);
    return value == null || value === "" || !Number.isFinite(parsed) ? null : parsed;
  }

  function validTimeMs(row) {
    const stamp = Date.parse(row?.valid_time_utc || "");
    return Number.isFinite(stamp) ? stamp : null;
  }

  function selectCommonValidTime(seriesByProvider, nowMs = Date.now()) {
    const cutoff = nowMs - GRACE_MS;
    const candidates = new Map();

    Object.entries(seriesByProvider || {}).forEach(([provider, rows]) => {
      (Array.isArray(rows) ? rows : []).forEach((row) => {
        const stamp = validTimeMs(row);
        if (stamp == null || stamp < cutoff || finiteNumber(row?.value) == null) return;
        if (!candidates.has(stamp)) candidates.set(stamp, new Map());
        const providerRows = candidates.get(stamp);
        if (!providerRows.has(provider)) providerRows.set(provider, row);
      });
    });

    const shared = [...candidates.entries()]
      .filter(([, rows]) => rows.size >= 2)
      .sort(([left], [right]) => left - right)[0];

    if (!shared) return { valid_time_utc: null, rows: {} };
    const [stamp, rows] = shared;
    return {
      valid_time_utc: new Date(stamp).toISOString(),
      rows: Object.fromEntries(rows),
    };
  }

  function runAgeHours(row, nowMs = Date.now()) {
    const init = Date.parse(row?.init_time_utc || "");
    return Number.isFinite(init) ? Math.max(0, (nowMs - init) / 3600000) : null;
  }

  function priorityState(row, health) {
    const states = [health?.ingest_state, health?.state, health?.freshness_state];
    if (row) {
      if (states.includes("error")) return "stale";
      if (["stale", "lagging", "degraded"].includes(health?.freshness_state)) return "stale";
      return "fresh";
    }
    if (states.includes("error")) return "error";
    return "pending";
  }

  function ensurePriorityStyles() {
    if (!root.document || root.document.getElementById("weathernext-priority-style")) return;
    const style = root.document.createElement("style");
    style.id = "weathernext-priority-style";
    style.textContent = [
      ".wn-primary{background:var(--hero);border:1px solid var(--accent);border-radius:14px;padding:14px;margin:12px 0}",
      ".wn-eyebrow{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--accent);font-weight:700}",
      ".wn-primary h2{font-size:21px;letter-spacing:-.4px;margin:4px 0 8px}",
      ".wn-status{display:inline-block;padding:5px 8px;border-radius:7px;background:var(--card);font-size:12px;font-weight:650}",
      ".state-pending{color:#d9e8f7;background:#16324a;border-color:#4b789c}",
      ".wn-primary p{font-size:12px;margin:8px 0 0;color:var(--ink)}",
      ".wn-primary .wn-note{font-size:11px;color:var(--muted)}",
      ".wn-value{display:block;font-size:26px;line-height:1.1;margin-top:8px}",
      ".wn-meta{overflow-wrap:anywhere}",
      ".provider{min-width:0}",
      ".provider-heading{min-width:0}",
      ".provider-heading>strong{min-width:0;overflow-wrap:anywhere}",
      ".provider small{display:block;min-width:0;overflow-wrap:anywhere}",
      ".provider .state-chip{flex:0 0 auto}",
    ].join("");
    root.document.head.appendChild(style);
  }

  function priorityCard(context) {
    const section = root.document.createElement("section");
    section.className = "wn-primary";
    section.dataset.weathernextPriority = context;
    section.dataset.state = "loading";
    section.setAttribute("aria-label", "WeatherNext 3 — primary research model");
    section.innerHTML = `
      <div class="wn-eyebrow">Primary research model</div>
      <h2>WeatherNext 3</h2>
      <span class="wn-status surface-state state-loading" role="status" aria-live="polite">LOADING · checking forecast availability</span>
      <strong class="wn-value" hidden>—</strong>
      <p class="wn-meta">Checking whether a WeatherNext forecast is available.</p>
      <p class="wn-note">Experimental forecast model. DWD warnings remain official.</p>`;
    return section;
  }

  function ensurePriorityCards() {
    if (!root.document) return [];
    ensurePriorityStyles();
    const overviewAnchor = root.document.querySelector('#overview [aria-labelledby="nextHoursTitle"]');
    if (overviewAnchor && !root.document.querySelector('[data-weathernext-priority="overview"]')) {
      overviewAnchor.parentNode.insertBefore(priorityCard("overview"), overviewAnchor);
    }
    const modelsView = root.document.querySelector("#models");
    const modelsAnchor = modelsView?.querySelector(".panel");
    if (modelsView && modelsAnchor && !root.document.querySelector('[data-weathernext-priority="models"]')) {
      modelsView.insertBefore(priorityCard("models"), modelsAnchor);
    }
    return [...root.document.querySelectorAll("[data-weathernext-priority]")];
  }

  function provenanceText(row) {
    if (!row) return "No genuine WeatherNext forecast value is available for this surface.";
    const parts = [
      `valid ${row.valid_time_utc || "unknown"}`,
      row.init_time_utc ? `init ${row.init_time_utc}` : "init unknown",
      row.lead_hours == null ? "lead unknown" : `lead ${row.lead_hours} h`,
      row.retrieved_at_utc ? `retrieved ${row.retrieved_at_utc}` : "retrieved unknown",
      `statistic ${row.statistic || "unknown"}`,
      `model version ${row.model_version || "unknown"}`,
    ];
    return parts.join(" · ");
  }

  function renderWeatherNextPriority(rows, healthMap) {
    const cards = ensurePriorityCards();
    const health = healthMap?.weathernext3 || {};
    const candidates = typeof root.canonicalProviderRows === "function"
      ? root.canonicalProviderRows(rows || [], "weathernext3")
      : (rows || []).filter((row) => row.provider === "weathernext3");
    const future = typeof root.futureRows === "function" ? root.futureRows(candidates, 48) : candidates;
    const row = future.find((item) => finiteNumber(item?.value) != null) || null;
    const state = priorityState(row, health);
    const healthState = health.ingest_state || health.freshness_state || health.state || "unknown";

    cards.forEach((card) => {
      card.dataset.state = state;
      const status = card.querySelector(".wn-status");
      const value = card.querySelector(".wn-value");
      const meta = card.querySelector(".wn-meta");
      status.className = `wn-status surface-state state-${state}`;
      if (row) {
        const numeric = finiteNumber(row.value);
        value.hidden = false;
        value.textContent = `${numeric.toFixed(1)}°`;
        status.textContent = state === "fresh"
          ? "AVAILABLE · WeatherNext forecast"
          : "DELAYED · WeatherNext forecast";
        meta.textContent = `Forecast for ${root.formatLocalTime(row.valid_time_utc)} · ${row.statistic || "forecast"}.`;
      } else {
        value.hidden = true;
        value.textContent = "—";
        if (state === "error") {
          status.textContent = "UNAVAILABLE · WeatherNext could not be refreshed";
        } else {
          status.textContent = "NOT AVAILABLE YET · WeatherNext forecast";
        }
        const homeSelected = (root.document.querySelector("#forecastLocation")?.value || "home") === "home";
        meta.textContent = homeSelected
          ? "No WeatherNext forecast for Home. Station 05480 research snapshots are separate."
          : "No matching WeatherNext forecast for this location and time.";
      }
    });
  }

  function observeTemperatureSurfaceFailure() {
    if (!root.document || typeof root.MutationObserver !== "function") return;
    const state = root.document.querySelector("#modelsTempState");
    if (!state || state.dataset.weathernextObserver === "true") return;
    state.dataset.weathernextObserver = "true";
    const sync = () => {
      if (!["error", "offline"].includes(state.dataset.state)) return;
      ensurePriorityCards().forEach((card) => {
        card.dataset.state = state.dataset.state;
        const status = card.querySelector(".wn-status");
        const value = card.querySelector(".wn-value");
        const meta = card.querySelector(".wn-meta");
        status.className = `wn-status surface-state state-${state.dataset.state}`;
        status.textContent = "UNAVAILABLE · WeatherNext could not be refreshed";
        value.hidden = true;
        value.textContent = "—";
        meta.textContent = "Try again later.";
      });
    };
    new root.MutationObserver(sync).observe(state, { attributes: true, childList: true, subtree: true });
    sync();
  }

  function installBrowserOverride() {
    if (typeof root.renderModelSnapshot !== "function"
        || typeof root.canonicalProviderRows !== "function"
        || typeof root.futureRows !== "function"
        || !root.document) return false;

    ensurePriorityCards();
    observeTemperatureSurfaceFailure();

    root.renderModelSnapshot = function renderAlignedModelSnapshot(rows, healthMap) {
      const seriesByProvider = Object.fromEntries(PROVIDERS.map((provider) => [
        provider,
        root.futureRows(root.canonicalProviderRows(rows, provider), 48),
      ]));
      const match = selectCommonValidTime(seriesByProvider);
      const comparisonTime = match.valid_time_utc;

      const cards = PROVIDERS.map((provider) => {
        const row = match.rows[provider] || null;
        const health = healthMap?.[provider] || {};
        const pending = provider === "weathernext3"
          && [health.ingest_state, health.state, health.freshness_state].includes("access_pending");
        const value = row && finiteNumber(row.value) != null ? `${finiteNumber(row.value).toFixed(1)}°` : "—";
        let note;
        if (pending) {
          note = "Not available yet";
        } else if (!comparisonTime) {
          note = "No matching forecast";
        } else if (!row) {
          note = `No forecast at ${root.formatLocalTime(comparisonTime)}`;
        } else {
          const age = runAgeHours(row);
          const init = row.init_time_utc ? ` · init ${root.formatLocalTime(row.init_time_utc)}` : "";
          const runAge = age == null ? "" : ` · run ${Math.round(age)}h old`;
          note = `${root.formatLocalTime(row.valid_time_utc)} · ${row.statistic || "deterministic"}${init}${runAge}`;
        }
        return `<div class="model-card${provider === "weathernext3" ? " primary" : ""}"><small>${root.escapeHtml(LABELS[provider])}</small><strong>${root.escapeHtml(value)}</strong><span>${root.escapeHtml(note)}</span></div>`;
      });

      root.document.querySelector("#modelSnapshot").innerHTML = cards.join("");
      const values = Object.values(match.rows)
        .map((row) => finiteNumber(row?.value))
        .filter((value) => value != null);
      root.document.querySelector("#modelSpread").textContent = comparisonTime && values.length >= 2
        ? `Model difference ${(Math.max(...values) - Math.min(...values)).toFixed(1)}° at ${root.formatLocalTime(comparisonTime)}`
        : "Model difference —";
      renderWeatherNextPriority(rows, healthMap);
    };
    return true;
  }

  const api = {
    finiteNumber,
    selectCommonValidTime,
    runAgeHours,
    priorityState,
    provenanceText,
    ensurePriorityCards,
    renderWeatherNextPriority,
  };
  root.RozkalnsModelComparison = api;
  if (typeof window !== "undefined") installBrowserOverride();
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
